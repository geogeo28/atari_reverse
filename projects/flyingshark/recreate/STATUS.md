# Reconstruction status — Flying Shark

Human-readable C reconstruction of Flying Shark (Taito / Firebird, 1987; the ST conversion by Prime
Software), each function **verified byte-for-byte against the original 68000 code** by the shared
differential harness (`tools/recreate_kit`: a Musashi oracle running the real code vs. the compiled
reconstruction, on the same memory image). `../names.txt` is the source of truth for every name.

**Verified: the sum of the per-section counts below.** That sum may be larger than the number of
FUNCTIONS, and deliberately: a row may be a SLICE filed under the address the slice starts at rather
than under a function's entry (README.md, "Adding a function", step 7). The total is written
nowhere: `test/test_status.py` re-derives each section's count from its rows, refuses a literal
grand total in this header, and refuses a `fn` line in `../names.txt` that is neither verified nor
deferred.

**ALL TEN SUBSYSTEMS ARE PORTED** — sprite, entity, player, weapons, hud and sound in waves 1 and
2, then `init`, `frontend`, `scroll` and `irq` in wave 3 — over the harness skeleton this file
opened with. Every section below has rows and a `src/<name>.c` beside it; what is left is accounted
for in "Not reconstructed, and why" rather than by absence, and that table's remaining rows are
model blockers and dead code rather than subsystems nobody has started.

**The image model is README's, not this file's.** Where the screen ring is placed, what the
post-load fixture holds and what it deliberately does not are decided in [`README.md`](README.md),
"The image model", and pinned by `test/test_image_model.py`. Nothing here restates it.

**How to add a function:** [`README.md`](README.md), "Adding a function" — the procedure, the file
ownership table and the conventions all live there rather than being restated here.

## Suite

**3,553 tests, all passing, no skips** — all fourteen files: `test_weapons.py` 902,
`test_entity.py` 745, `test_player.py` 724, `test_hud.py` 333, `test_sound.py` 269,
`test_sprite.py` 205, `test_frontend.py` 106, `test_irq.py` 80, `test_init.py` 76,
`test_scroll.py` 62, `test_image_model.py` 30, `test_constants.py` 8, `test_heap_guard.py` 8,
`test_status.py` 5. Measured 2026-09-07 with
`rm -f build/*.so && find . -name __pycache__ -exec rm -rf {} + && make test`. `make guarded` runs
the same 3,553 (Darwin/BSD only) and reports **10,804 guarded candidate runs** across its workers —
every case whose candidate indexes the image with an address it computed.

NOTHING SKIPS ANY MORE. The four skips this file opened with were the gates that arm on the first
row anyone files, and all four armed in wave 1: `test_status.py::test_every_named_function_is_
verified_or_deferred` accounts for the whole of `../names.txt`, and `test_constants.py`'s three
battery gates now have TEN `src/*.c` and ten batteries to check.

Re-sum this line at every merge rather than carrying it (`docs/agent-playbook.md` §12): each wave
reports its own count, and a headline nobody recomputes stays at whichever wave last wrote it. The
kit's own suite behind it is `make -C tools/recreate_kit test`, a number that moves with the kit
rather than with this project — re-run it rather than quoting it.

**Mutations tried against the skeleton's gates**, each from a clean `build/` with `__pycache__`
swept and the candidate `.so` relinked (`docs/agent-playbook.md` §10), and each **red**, killed by
the case named:

| mutation | killed by |
|---|---|
| `conftest.STOP_TITLE_COPY` moved one instruction early (0x1127e -> 0x11278) | `test_this_files_own_pins` — `check_entry_prologues(conftest)`, the bytes at the address |
| `conftest.ENTRY_LEVEL0_ASSETS` moved past `load_level_assets` (0x112ac -> 0x112b2) | 8 cases: the prologue pin, the replay/transcription diff, five `load_file` placements and `test_the_fixture_is_not_the_bare_image` |
| `MODULE_OVER_ARENA_BYTES` 9 -> 8 in BOTH `include/globals.h` and the mirror | `test_the_sound_module_overlaps_the_entity_arena_by_nine_bytes` — the size is re-derived from the record's own length, so a matched pair does not agree its way past |
| `SCREEN_RING_2_OFF` 0x17700 -> 0x17600 in BOTH the header and `conftest` | `test_the_boot_slice_derives_the_ring_from_its_own_physbase` |
| `conftest.ring_pointers` drops the `clr.b` rounding | `test_the_ring_arithmetic_is_the_originals_at_a_physbase_of_our_own[unaligned]` — and NOTHING ELSE: every Physbase the fixture uses is already 256-aligned, so this SURVIVED until that case was added (measured 2026-09-07) |
| `conftest.ring_pointers` drops the `+0x100` before the mask | 5 cases, both ring pins among them |
| `install_boot_state` drops the `st $176ea` store | `test_the_replay_and_the_transcription_agree` — which is how that store was found missing in the first place |
| `install_boot_state` installs `$70` before it reads it | the same case |
| `install_boot_state`'s sprite-directory relocation adds nothing | the same case |
| the fixture keeps the harness's staged files | `test_the_fixture_carries_no_staged_files`, and the same case |
| `TITLE_COPY_BYTES` 32,000 -> 31,996 | `test_the_replay_carries_the_title_picture_the_transcription_skips` — and only since it pins the band against `SCREEN_BYTES` and the record's length: a NEOchrome picture ends in zeroes, which the transcription's zeroes agree with, so the band's edge SURVIVED a four-byte trim before that (measured 2026-09-07) |
| `TITLE_COPY_OFFSET` 0x80 -> 0x40 | the same case, and the replay/transcription diff |
| `test_the_loaded_image_...` skips the 1,563 relocation fixups | `test_the_loaded_image_holds_the_prgs_own_text_and_data` — it builds TEXT+DATA from the file, so the loader is not both sides of it |
| `abi.SCREEN_RING_PHYSBASE` moved to 0x7f900 | `test_the_ring_placement_is_the_originals_arithmetic` (+1) — boot_init rounds STRICTLY up, so the ring would land at 0x60100 |
| `conftest.SEEDED_POINTERS` seeds `screen_draw` from ring[0] | `test_the_boot_slice_derives_the_ring_from_its_own_physbase` |
| `A_tile_banks` taken from `../names.txt`'s `cmt 0x16346` (0x28928) | `test_the_records_name_the_addresses_globals_h_states` (+1) — the records are read out of the relocated image |
| the autouse base-image fixture made non-autouse | `test_every_differential_starts_from_the_post_load_image` |
| `abi.STUB` moved into the screen ring | `test_the_scratch_map_is_clear_of_the_program_the_ring_and_the_file_table` (+1) |
| a `## Verified — <x> (N)` count raised by one | `test_status.py::test_every_section_states_its_own_row_count` |
| `project.toml`'s `tos_malloc_unused` removed | the kit refuses at IMPORT — the whole suite errors, naming `heap_base`, the program's 0x5aede end and the waiver itself |
| `conftest.SPRITE_RECORDS` halved to 128 | `test_this_files_own_pins` (+2) — the CLAUDE.md §5 mirror against `include/globals.h`; without it the fixture would compare only the half it relocated |
| `SPRITE_RESTORE_LISTS` halved to 2 in BOTH the header and `conftest` | `test_the_sprite_directory_relocation_is_the_originals` (+1) — it checks the ORIGINAL wrote no fifth terminator, so a matched pair of wrong constants does not agree its way past |
| `conftest.ENTRY_BOOT_INIT` moved two bytes on | `test_this_files_own_pins` — the entry prologue read off the loaded image |
| `test_image_model`'s `A_sprite_bank` mirror moved two bytes on | `test_this_files_own_pins` (+4) |

## Verified — init (13)

Wave 3's init slice: the boot chain, the file loader, the three palette wrappers, the two resets,
and ONE PASS OF THE FRAME LOOP — the integration test of the whole port.

THIS SECTION VERIFIES THE ROUTINES `test/conftest.py` REPLAYS. The fixture every other battery runs
on is built by putting `boot_init` and `init_load_assets` under the oracle; these rows are the same
routines' RECONSTRUCTIONS diffed against the same original, so a divergence between the fixture and
the port shows up as a case in `test_init.py` rather than as a fixture nobody re-derives.

**THE FRAME LOOP IS THE HEADLINE.** `frame_loop_once` @ 0x1575c calls the forty-five verified cores
in `main`'s own order and one case diffs a WHOLE FRAME of a stage the ORIGINAL started — four
screens in the ring, 223 display records, the entity arena, the HUD's digits, the sound module's
state and the PSG's register stream. Twelve frames are verified, in THREE WINDOWS CUT FROM ONE
CONTINUOUS PLAY-THROUGH of a level the game itself set up (`init_stage_state` @ 0x1139a run to its
`rts`, which falls through `difficulty_apply_fire_rates` into `start_level`), plus three entered the
way a stage restart leaves one. Nothing in the staging writes a game byte itself: every frame after
the first is the previous frame run through the ORIGINAL's loop.

**THE THIRD WINDOW IS THE BOMB CHAIN'S, and it is what makes four of the forty-five do anything.**
`bomb_fall_step`, `bomb_publish`, `bomb_blast_step` and `bomb_blast_vs_entities` all return at their
first guard on a frame with no bomb in the air, which every quiet and busy frame is. So the
play-through holds the keyboard's bomb key (`key_bits` bit 5) from frame 182 — the frame after the
busy window closes — and the third window is four frames of the blast that follows, entered with
`bomb_exploding` set and `blast_step` between 1 and 14.
`test_the_blast_window_really_has_a_blast_going_off` asserts both on every frame of it, so a window
that drifted a bomb-cycle either way would fail rather than quietly become the busy one again.

**THREE REGISTER CARRIES, MEASURED.** Two of the forty-five read registers their PREDECESSOR in the
loop left rather than ones their own code sets — three registers between them. `bomb_blast_step`
indexes `A_blast_offset_tbl` with the high word of a D0 it never writes (`src/weapons.c` argues the
dependency; this is its only call site), and `player_publish` passes D1 and D2 on to the game-over
banner's text script. `test_the_frame_loops_register_carries_are_what_the_original_leaves` reads all
three out of the ORACLE at the two call sites over every staged frame rather than asserting them, so
a change in any predecessor fails by name. What it measures: D1 and D2 are zero throughout, and D0's
HIGH word — the half that reaches the table — is zero on all twelve staged frames while its LOW word
is not (0x9d and 0xd3..0xd5 are what the predecessors leave, and `bomb_blast_step`'s own
`move.w $176ec,d0` overwrites it before the `adda.l`). The BLAST window is why the figure is worth
measuring at all: it is the only one of the three windows in which the routine gets past its
`bomb_exploding` guard and actually indexes with it.

**THE CALL ORDER IS PINNED AT THE SOURCE, because the byte diff cannot see it.** Dropping
`level2_scenery_effect_gate` (it returns at once outside level 2) and swapping two neighbours that
commute on a given frame BOTH SURVIVED the whole battery (measured 2026-09-07). So
`test_frame_loop_once_calls_those_routines_in_that_order` reads `src/init.c`'s call list and matches
it name-for-name against `../names.txt`'s name for each of the original's forty-five `bsr.w`
targets. It is a source pin and is worth exactly what it says; that the routines themselves are
right is the other sections of this file.

**TWO ARMS THE VERIFIED FRAMES DO NOT REACH**, and neither is a matter of staging: both leave the
loop by UNWINDING THE STACK rather than returning — `read_player_input`'s abort key
(`adda.l #$40,a7`) and `level_progress_check`'s level-advance (`addq.l #4,a7 / bra.w $15758`) — and
a C function cannot express either. A third, the player's death, reaches
`restart_level_at_checkpoint` and branches back to the loop's TOP, so the oracle would make two
passes where the candidate makes one; `test_init.py`'s staging watches the life count and refuses to
hand out such a frame rather than producing one.

**THE BOOT CHAIN MOVES THE STACK ONTO THE GAME'S OWN**, `movea.l #$19094,a7`, so the oracle's trap
frames land inside the PROGRAM and the candidate — C, with no machine stack — writes none of them.
The two `boot_init` cases exclude that band and `test_the_boot_stack_band_is_the_one_the_oracle_
really_used` pins its depth against the oracle's own `min_a7`, because the harness only checks that
an exclude band REACHES the stack and a band twice as deep would hide any store below it.

**TWO XBIOS CALLS HAVE NO `os_*` DOOR** — `Physbase` and `Kbdvbase` — so `src/init.c` reads
`OS_SCREEN_BASE` and `OS_KBDVBASE` out of the same `os.h` the shim answers them from. The
differential is the real pin (the ring values and the joyvec store are derived from them);
`test_the_two_undoored_xbios_answers_are_the_models_own` adds the two facts a diff cannot state. The
gap is a row in "Follow-ups the kit should absorb".

**A FINDING IN THE SHIPPED DATA.** `A\LEVEL1.MAP`'s record asks `load_file` for 0x1388 bytes to
0x16432, which runs to 0x177ba — over `load_dest`, `load_len` and `load_file_handle`, the loader's
own three scratch longwords. The file is 3,664 bytes and GEMDOS's SHORT READ is the only thing
between the routine and closing a handle it has just overwritten with map data.
`test_a_records_length_can_exceed_its_files` asserts the arithmetic rather than merely observing it,
so a level map that grew would fail there.


**Mutations tried**, each from a green baseline with `build/` and `__pycache__` swept and the
candidate relinked (`docs/agent-playbook.md` §10). Three SURVIVED and each is recorded rather than
worked around: two were closed by adding the case named, and the third cannot be closed off target.

| mutation | result |
|---|---|
| `TITLE_COPY_LONGS` 0x1f40 -> 0x1f3f | red — `test_the_title_slice_loads_the_picture_and_copies_it_to_the_screen` |
| `TITLE_COPY_OFFSET` 0x80 -> 0x40 | red — the same case |
| the title slice makes only ONE `Setpalette` | red — the same case, through the OS event ledger |
| `boot_init` drops the `move.l $70,$11650` chain-operand save | red — `test_boot_init_builds_the_machine_the_fixture_is_made_of` |
| the ring's `addi.l #$100` rounding dropped | red — the same case |
| the ring's 256-byte MASK dropped (`clr.b d0`) | red — `test_the_ring_derivation_rounds_at_a_physbase_the_model_cannot_answer_with[unaligned]`, and NOTHING ELSE (1 failed / 3,552 passed): every Physbase `boot_init` itself can be run at is already 256-aligned once the `subi.l` and the `addi.l` are done with it, so the mask changes nothing there. It survived the whole battery until that case existed |
| the frame loop passes a NON-ZERO high word in D0 to `bomb_blast_step` | red — the four `test_a_whole_frame_with_the_smart_bomb_going_off` cases and `test_a_frame_entered_the_way_a_stage_restart_leaves_one[blast]`, and NOTHING ELSE (5 failed / 3,548 passed). On a quiet or busy frame the routine returns at its `bomb_exploding` guard before it indexes anything, so the carry has no surface there at all |
| the boot `Setscreen`'s logical and physical bases swapped | red — the same case, through the event ledger (only the LOGICAL base is in it) |
| `load_file` drops the handle store | red — the same case |
| `load_file`'s destination and length swapped | red — the same case |
| `clear_actor_arrays` stops one byte early | red — `test_clear_actor_arrays_clears_to_the_end_of_the_program` |
| `NEW_GAME_LIVES` 5 -> 4 | red — `test_init_new_game_resets_the_per_game_state` |
| `init_new_game` drops the `max_weapon_flag` guard | red — the same case's other arm |
| `init_new_game` never calls `clear_actor_arrays` | red — the same case |
| `STAGE_SCROLL_POS_SEED` 0x2e -> 0x2c | red — `test_init_stage_state_resets_the_per_stage_state` |
| `init_stage_state` drops the `keep_player_hit_flag` guard | red — the same case's other arm |
| `probe_disc` opens the CALLER's record | red — `test_probe_disc_ignores_its_callers_record` |
| `set_palette_game` names the title table | red — `test_a_palette_wrapper_is_its_setpalette_and_nothing_else`, event ledger only |
| the sprite directory relocates 128 records | red — `test_the_sprite_slice_loads_the_bank_and_relocates_its_directory` |
| the four restore-list terminators are not written | **SURVIVED** until that case poked the fixture's own four terminators away — the boot chain has already written them, so a reconstruction writing none of them agreed over all four |
| the frame loop drops `clr.w level_just_started` | **SURVIVED** every ordinary frame — the flag is already zero — until `test_a_frame_entered_the_way_a_stage_restart_leaves_one` entered one with it SET |
| the frame loop drops `level2_scenery_effect_gate` | **SURVIVED** the whole battery: the gate returns at once outside level 2. Closed by `test_frame_loop_once_calls_those_routines_in_that_order`, the source-level order pin |
| the frame loop swaps two adjacent calls | **SURVIVED** the byte diff for the same reason (the two commute on the staged frames); the order pin is what kills it |
| `probe_disc` closes a NEGATIVE handle too | **SURVIVED, and cannot be killed off target** — see "Unpinned on target" |
| `boot_init` drops the `clr.w cheat_used_flag` | **SURVIVED** — the byte ships as 0 and nothing in the fixture chain writes it, so the store was 0 over 0. Closed by seeding it in `test_boot_init_over_the_bare_loaded_image` |
| `boot_init` never saves TOS's old joyvec | **SURVIVED** — that same case was zeroing the SOURCE (`OS_KBDVBASE + 0x18`) as well as the destination, so the copy had nothing to copy. Closed by seeding the source with a sentinel instead |
| `clear_actor_arrays` clears ONE BYTE TOO MANY (`<` -> `<=`) | **SURVIVED** — the byte at `FS_PROGRAM_END` is 0 in the image, so the extra clear wrote 0 over 0 and the guard byte was only below the arena. Closed by putting a second guard byte ABOVE the limit |
| any of TWELVE `clr.w`s in `init_new_game` (the six extra bonus-life flags, the three loop flags, `name_entry_first_pass`, `hiscore_beaten`, `item_pickup_pending`) | **SURVIVED** — every one of those words is zero in the shipped `.PRG` and nothing in the boot chain writes it, so a dropped store wrote 0 over 0. Closed by `test_init_new_game_over_random_prior_state`, which pokes all nineteen words the reset writes to junk first |
| `load_file`'s `Fclose` given the REGISTER instead of the stored word | **SURVIVED, and cannot be killed**: the two are one value unless the load overwrote `A_load_file_handle`, and the only record that reaches it (a full-length `A\LEVEL1.MAP`) reaches the HANDLE word before `load_dest`, so the `Fclose` that follows is refused and the run is thrown away rather than differing. `_staged_record`'s docstring carries the argument |
| the two `clr.l` cursors cleared as WORDS | **SURVIVED** — the stage fuzz poked two bytes at each, so the low word kept its zero. Closed by poking all four bytes at `A_spawn_script_cursor` and `A_bomb_path_cursor` |

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10000` | `entry_stub` | 4 | ✅ verified | SLICE [0x10000, 0x14d06) — the .PRG's entry point is `bra.w boot_init` and nothing else, so this is the row below entered one branch earlier. The branch stores nothing; what it adds is that the operand really names `boot_init` rather than the 44-byte plaintext banner at 0x10004 |
| `0x10bfa` | `load_file` | 82 | ✅ verified | All EIGHT asset records, each staged with content of the test's own choosing so the `Fread` is visible over a fixture that already holds every file at its destination. Destinations and lengths are read out of the image (both longwords are relocated). The short-read case above, and poison on the three scratch longwords. Mutations: a dropped handle store and a dest/len swap are red |
| `0x10c4c` | `probe_disc` | 64 | ✅ verified | Driven with all eight records in A0, which is what tests that it IGNORES its caller and opens its own `A\SPRITES.cru`: seven of them would name a file nothing staged and be REFUSED rather than merely differ. Poison on the longword result. Its NEGATIVE arm cannot be run off target — see "Unpinned on target" |
| `0x111a6` | `set_palette_black` | 24 | ✅ verified | Writes no image byte at all: the ordered OS EVENT is the whole surface, and a wrapper that named a neighbour's table is separable there and nowhere else. Mutation: `set_palette_game` pointed at the title table is red |
| `0x111be` | `set_palette_game` | 24 | ✅ verified | The same shape at `A_palette_game` |
| `0x111d6` | `set_palette_title` | 24 | ✅ verified | The same shape at `A_palette_title`. Also reached as the first instruction of `init_load_assets` |
| `0x11212` | `init_load_assets` | 108 | ✅ verified | SLICE [0x11212, 0x1127e) — the title picture: the palette, `A\FLY_SHK.NEO`, the NEO palette at header + 4, the Setscreen and the 32,000-byte copy to `Physbase - 0x80`. The picture is staged with the test's own bytes, because the fixture already holds `A\SPRITES.cru` at the same destination. Mutations: the copy one longword short, the offset halved and a dropped second Setpalette are red |
| `0x112b2` | `init_load_assets` | 72 | ✅ verified | SLICE [0x112b2, 0x112fa) — the sprite bank: the level-0 flag, `A\SPRITES.cru` read RAW over the title picture, 256 directory pointers relocated in place and four restore-list terminators. A SECOND slice because the `bsr.w load_level_assets` @ 0x112ae between the two is the frontend subsystem's. The four terminators are poked away first: the boot chain has already written them into the fixture, and without that a reconstruction writing none of them agreed over all four (measured) |
| `0x112fa` | `init_new_game` | 154 | ✅ verified | SLICE [0x112fa, 0x11394) — it ends `bra.w enter_title` and never returns to `main`. Both arms of its one branch (the "J H" cheat's `max_weapon_flag`), and a case that REWRITES `A_const_words_0123`, which four of its stores read their value from instead of using an immediate. Mutations: the life count, a dropped guard and a dropped `clear_actor_arrays` are red |
| `0x1139a` | `init_stage_state` | 158 | ✅ verified | SLICE [0x1139a, 0x11438) — it ends in a DISPATCH, not a return: `tst.b hard_mode / beq.w $12cb6 / bra.w $12cc8` picks between the two entries of `difficulty_apply_fire_rates`, each of which falls into `start_level`. Both arms of the `keep_player_hit_flag` guard (its set arm is CONTRACT coverage — nothing in the image writes that flag), and a sharded fuzz that pokes every word it writes to junk first |
| `0x115e2` | `clear_actor_arrays` | 26 | ✅ verified | 0x59984..0x5aedd over an arena seeded non-zero throughout, with a guard byte below it, plus poison. The loop is a DO-WHILE and its limit is the program's own end. Mutation: one byte short is red |
| `0x14bee` | `boot_init` | 280 | ✅ verified | SLICE [0x14bee, 0x14d06) — the whole routine up to `bra.w main`: Super's token, the nine screen pointers, `A\MODULE.BAK`, the two exception vectors and the chain operand, the IKBD joystick-report command and TOS's displaced joyvec. Run twice — on the post-load fixture, and on one with the whole of its own output poked back to zero, which is what separates "wrote it" from "it was already there". PLUS THE RING DERIVATION ON ITS OWN, entered at 0x14c26 with the Physbase in the case's hands (`g_derive_screen_ring`, D0), at three of them: the harness's, the model's, and one whose ring base is NOT 256-aligned. That last one is the only thing in the project that drives the `clr.b` — every Physbase `boot_init` itself can run at is already aligned — and the nine longwords are poisoned first. Mutations: a dropped chain-operand save, a Setscreen argument swap and the ring's `addi.l #$100` are red; the MASK is red only at the unaligned Physbase (measured) |
| `0x1575c` | `frame_loop_once` | 186 | ✅ verified | SLICE [0x1575c, 0x15816) — one pass of `main`'s endless loop: forty-five `bsr.w`s and the `clr.w level_just_started` that ends it. Fifteen whole-frame cases over three windows of a stage the ORIGINAL started — quiet, busy, and the bomb chain's blast — plus the source-level order pin and the register-carry measurement described above. Mutations: a dropped call, a swapped pair, a dropped final clear and a non-zero D0 high word into `bomb_blast_step` are all red — each only since the case that reaches it was added |

## Verified — frontend (6)

Wave 3's front-end slice: the asset loader's filename patch, the attract screen's stage start, level
2's scenery band, the debug key wait and the hall-of-fame name entry.

**FOUR OF THE SIX ARE SLICES, and the reason is the title flow's SHAPE.** It never returns to
anybody — `hiscore_name_entry`'s every arm ends `bra.w $10720`, back into `title_frame_step`, and
the attract loop past 0x1054a is one spin with four exits — so each slice is diffed at a checkpoint
PC and the `[start, end)` span is in its row. The three routines the spans skip past
(`set_palette_black` @ 0x111a6, `set_palette_game` @ 0x111be and `load_file` @ 0x10bfa) were the
`init` subsystem's and unported when the spans were chosen; all three are verified now, which is why
"Not reconstructed"'s row for the title flow no longer says the slice is waiting on them.

**THE ATTRACT SCREEN'S STAGE START IS THE SCROLL SUBSYSTEM'S CODE.** `title_attract_loop` @ 0x10508
and 0x1052a are byte-identical copies of `start_level` @ 0x1151e and 0x11544 — the map-cursor seed
and the prescroll loop — so `src/frontend.c` calls `seed_map_row_cursor` and `prescroll_stage`
(`include/scroll.h`) rather than restating them, and `test_scroll.py` runs every case of both at
BOTH addresses. That the two copies are the same code is therefore something the differential
settles rather than something the reconstruction assumes; the `title` half of those cases is counted
with the 0x104f6 row's subsystem here only in prose, and with `scroll`'s rows in the ledger.

**THE SCENERY BAND IS ALSO VERIFIED AT THE HEIGHT THE GAME ITSELF REACHES.** Every poked case drives
one arm at a time and none of them reaches more than three whole tile rows; the window the GAME runs
is 204 frames long (`level_distance` 0x8a2..0x96e, one frame each) and ends at SIX whole rows and six
scanlines, with the band's offset having WRAPPED — seeded 0x8100, 0xa0 subtracted a frame, so it
starts 32,512 bytes ABOVE `screen_draw` and is 0x180 BELOW it by the last growing frame. A session
fixture replays the ORIGINAL's own effect across that whole window and hands the last two frames out
as pokes; `test_the_replayed_window_reaches_the_band_the_measurement_names` is the positive control
on it, and the two differentials write 30,912 bytes of screen through an address the routine
computed — which is why `make guarded` is the bound on them.

**`hiscore_name_entry` WAS THE HUD SLICE'S DEFERRAL and is closed.** Its two mid-routine `bsr`s into
the sound module's sfx wrappers were the whole of the reason it was deferred; with `src/sound.c`
landed those are one call each, and a whole-slice differential runs. Its confirming arm calls
`check_cheat_name` @ 0x10d92 — the hud subsystem's core — whose own arm spin reads `key_bits`
through the kit's scheduled-write model, so those cases carry a schedule for a wait site inside a
routine they call.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x1003c` | `level2_scenery_effect` | 652 | ✅ verified | 44 cases. The three-part window as a SIGNED compare — below it (including the negative `level_distance` every attract loop really runs on), above it, and the three frames the two `bgt`s separate; the reset frame, where `clr.l $1779e` clears the whole-row count AND the partial-row count as one longword over two adjacent words; the growing carry at every partial count including the deliberate 0xffff that makes the following `addq` land on 0; the shrinking borrow and the `bpl` past the `clr.w` that the odd counts reach; both blit loops at four row/partial shapes; five tile-id sets including 0x80, where the WORD shift wraps the offset to zero, and 0x40..0x7f, where the `adda.w` sign-extends it NEGATIVE; five band offsets including the 0x8100 seed, which is negative and puts the band ABOVE `screen_draw`; and a 72-case sharded fuzz over all of it. PLUS THE BAND THE GAME ITSELF REACHES: the last growing frame and the first shrinking one at six whole rows and a WRAPPED (positive) offset, staged by replaying the original's own effect across the whole 204-frame window and pinned by a positive control on what that replay left. Every case indexes the screen ring with an address the routine computed, so `make guarded` is the bound. Mutation: an INVENTED four-row bound on the band — one of `docs/methodology.md`'s six "green differential, unfaithful arm" shapes — is red under those two cases and NOTHING ELSE (2 failed / 3,551 passed), because no poked case reaches more than three whole rows |
| `0x10332` | `load_level_assets` | 64 | ✅ verified | SLICE [0x10332, 0x10372) — the five filename digits, ending at the first `bsr load_file`, which is the `init` subsystem's. All five levels out of the .PRG's own `level_bank_digits`, one level's row seeded so no shipped digit could stand in for another, and four out-of-range level numbers that pin `muls.w #$5` as SIGNED. Poisoned, so a candidate that wrote no digit could not pass on the shipped names |
| `0x104f6` | `title_attract_loop` | 84 | ✅ verified | SLICE [0x104f6, 0x1054a) — the attract screen's stage start, entered one instruction past the `bsr set_palette_black` the `init` subsystem owns and ending where the attract poll begins. Scroll position back to zero out of `const_words_0123`, scroll phase to 0x1e, the map cursor to the end of the map, and the screen scrolled in with `prescroll_flag` set: four frame counts including 0, which still draws ONE frame, 16, where the phase wraps and the cursor steps, and the count the binary ships — 108 calls to `render_frame`, which is the machine `test_sprite.py` stages its own cases on. One more case pokes `const_words_0123[0]` to something other than zero and watches the scroll position follow it — `move.w $176ac,$17758` is a READ of that table, not a `clr.w`, and the prescroll then draws a different stretch of the map. The two shared blocks inside the slice are additionally verified at this site by `test_scroll.py`'s `title` parametrisation |
| `0x10916` | `hiscore_name_entry` | 236 | ✅ verified | SLICE [0x10916, 0x10720) — it never returns; every arm branches into `title_frame_step`. 38 cases: the once-per-name space fill and the `st` that is a BYTE store into a word `tst.w` reads; the glyph step forward at every cursor position and back, with both wraps; the arms' ORDER (right over left, either direction over fire), which an if/else chain has and a set of independent tests would not; the confirm that COPIES THE GLYPH FORWARD so the next initial starts as this one; the third fire through `check_cheat_name` with the arm key up and with it down on a real cheat name; three ranks including the lowest; the countdown as a SIGN test, so 0x8000 steps to 0x7fff and is still positive; and an 84-case sharded fuzz over the stick, both flags, the cursor, the rank and the timeout. The countdown's reset writes `new_hiscore_pending` out of `const_words_0123[0]`, which is a 0 over a 0 on every other case: one case REWRITES that table word, and a mutation that spells the store as an immediate 0 is red under it alone (1 failed / 3,552 passed) |
| `0x10bc8` | `level2_scenery_effect_gate` | 16 | ✅ verified | four level numbers: the effect runs on level 2 alone, and the others return having written nothing even with `level_distance` inside the window — which is why the gate is a routine and not a test inside the effect |
| `0x11ba2` | `debug_wait_for_keypad4` | 20 | ✅ verified | It WRITES NOTHING, so the only thing a case can compare is how many times it read `key_bits` — the kit's scheduled-write model against the oracle's arrivals at the same PC. Four arrival points including "already down", and one case with every OTHER bit of the byte held, which a wait that tested the whole byte would end on. NO CALLER in the image: a leftover single-step hook, verified because it is reachable under the oracle and cheap to pin |

## Verified — scroll (5)

Wave 3's scroll slice: the frame loop's scroll step, and what a stage start does to the map cursor
and to the screen.

**`start_level` @ 0x11440 HAS NO WHOLE-ROUTINE ROW**, and one of its two reasons has since gone.
It ends `bra.w music_play` rather than returning, so there is no `rts` a whole-routine case could
stop at — that is structural. It also calls `clear_actor_arrays` @ 0x115e2, `set_palette_black`
@ 0x111a6 and `set_palette_game` @ 0x111be, which were the `init` subsystem's and unported when
these four spans were chosen; all three are verified now, so ONE case entered at 0x11440 and diffed
at the closing `bra` is available — it is the follow-up row below, not a blocker. The four rows here
carry their spans, and the row for 0x11440 is the routine's entry.

**Follow-up (not a blocker):** fold the four spans into one whole-routine case at
`[0x11440, 0x11564]`, stopped at `bra.w music_play`. It would cover the three `bsr`s and the ~140
bytes of `load_level_assets` call sequence between 0x11494 and 0x1151e that no span claims today.
Doing it means retiring four ✅ rows for one, which is a ledger change rather than a port.

**TWO OF THESE CORES ARE VERIFIED AT TWO ADDRESSES EACH.** `seed_map_row_cursor` and
`prescroll_stage` are the blocks `title_attract_loop` @ 0x10508 / 0x1052a and `start_level`
@ 0x1151e / 0x11544 carry one copy of each, and `src/scroll.c` has one core for each rather than two.
Every case runs at both entries, so a difference between the original's copies would fail at
whichever site it is in; the ledger files each core under `start_level`'s address, because the title
screen's copies are inside `frontend`'s 0x104f6 slice and one span may not be claimed twice.

**`A_scroll_pos` AND THE SCROLLER BLOCK LIVE HERE NOW.** `include/scroll.h` owns 0x163da..0x16436
(less `A_level_number`, which is the level-flow state `include/player.h` owns) plus `A_scroll_pos`
and `A_level_distance`; the five "Borrowed globals" rows that held them in `include/sprite.h` and
`include/hud.h` were deleted with the defines, and both headers now include this one.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x111ee` | `scroll_advance` | 36 | ✅ verified | the whole routine, poisoned: two pixels of scroll and `level_distance = ((scroll_pos - 0x30) >> 1) + 1` in 16 bits, at ten positions — both sides of the bias, the word wrap of the `addi.w`, and the halving's own sign boundary — plus a 320-case sharded fuzz over every position. THE SHIFT IS LOGICAL, which is what the sub-bias positions pin: the title screen seeds `scroll_pos` to 0 and really does run its first two dozen frames with `level_distance` up near 0xffff, and an `asr.w` would agree with every case at or above the bias |
| `0x11440` | `start_level` | 26 | ✅ verified | SLICE [0x11440, 0x1145a) — the bomb count and the three per-stage resets, ending at the `bsr clear_actor_arrays` the `init` subsystem owns. Run on a started game with the count dirtied, and once more with `const_words_0123[3]` poked to something else: `move.w $176b2,$17710` is a READ of that table and not an immediate 3, which is what the second case separates |
| `0x1145e` | `start_level` | 54 | ✅ verified | SLICE [0x1145e, 0x11494) — the object list cleared and the level's own 20-byte record copied into the four live parameters. All five records out of the .PRG's own `level_table`, one record seeded whole so no shipped field could stand in for another, and four out-of-range level numbers that pin `muls.w #$14` as SIGNED — the routine has neither floor nor ceiling. Poisoned over all four destinations |
| `0x1151e` | `start_level` | 34 | ✅ verified | SLICE [0x1151e, 0x11540) — `seed_map_row_cursor`: the map cursor and its saved copy set to one past the END of the map, the game scrolling upward. The shipped LEVEL1.MAP header plus nine poked ones, poisoned, AT BOTH SITES (this one and `title_attract_loop` @ 0x10508, which holds the same ten bytes): row counts to 0xffff, where `mulu.w` is a 16x16 -> 32 the product needs, and a column count of 0x8000, where the `asl.w #1` wraps the STRIDE to zero before the multiply — the one case that separates a word doubling from a long one |
| `0x11544` | `start_level` | 32 | ✅ verified | SLICE [0x11544, 0x11564) — `prescroll_stage`: `prescroll_flag` set, `prescroll_frames + 1` calls to `render_frame`, flag cleared. AT BOTH SITES again (this one and `title_attract_loop` @ 0x1052a). Four frame counts including 0, which still draws ONE frame because of the `dbf`, and 16, a whole tile row of scroll — so the phase wraps and the map cursor steps inside the run; the flag is poked to a value that is neither the 1 the routine writes nor the 0 it clears, so both stores must happen. `test_the_seed_staging_is_the_originals_own_work` pins that the map cursor these cases run on was written by the ORIGINAL's own seed slice and that the slice touched nothing else |

## Verified — sprite (20)

Wave 1's sprite slice: `render_frame` @ 0x14446 — the 45th and last call of the frame loop — and
every routine it draws through. `include/display_list.h` carries the FROZEN layouts the whole game
publishes into: the 223 six-byte display records, the six-byte restore record, and the tile repair
grid. Every field is tagged `pinned by <test>` or `names.txt, unpinned`, and a publisher includes
that header to READ a field rather than restating one.

ONE BODY, TWELVE ENTRY POINTS. The four masked blitters and their eight clipped variants are the
same unrolled loop at four widths with an optional per-group gate, so `src/sprite.c` has one
`blit_sprite_rows` and twelve thin entries over it; the eight clip LADDERS are transcribed as tables
because two of the four right-hand ones are irregular (below). `render_frame` dispatches on the
width class directly instead of `jsr`ing through the four tables, and
`test_the_blit_tables_name_the_routines_this_file_dispatches_to` reads all seventeen longwords out
of the loaded image to say that is the same call.

THREE FINDINGS THAT CONTRADICT `../names.txt` OR `../notes/gameplay.md`, each with the instruction
that settles it, are written up in `../out/names_sprite_port.txt`: `restore_blit_tbl` has FIVE
entries and `restore_blit_w16` IS reached through it (`move.w #$4,-4(a5)` @ 0x14e10 and 0x14ef8);
`tile_split_row_table` is sixteen pairs, not five; and `scroll_wrap_copy_1280` copies 320 bytes, the
1280 being the total over its four call sites.

TWO ORIGINAL BUGS, reproduced and not repaired. (1) The right-edge clip ladders of width classes 0
and 1 narrow the restore record they have just appended; those of classes 2 and 3 do not — so
`sprite_blit_w48_clip_right` at x = 0x120 draws two of its four groups and still restores all four,
16 bytes past the row's end into the left edge of the row below, and at x = 0x130 it draws ONE and
overruns by 24. (2) `render_frame`'s map-pointer reset arm is dead twice over: 0x147da is a `nop`
where the bound test was, so the store it guarded always runs, and 0x147e6 overwrites it two
instructions later. Both stores are spelt out in `advance_scroll`.

**How the frame cases are staged.** `render_frame` is not a leaf, so its cases run on a MID-LEVEL
image the ORIGINAL built: `title_attract_loop` @ 0x104f6 -> 0x10544 replayed under the oracle from
the post-load fixture, which is 108 calls to `render_frame` with `prescroll_flag` set. That leaves
real terrain in all four screens, `map_row_ptr` seven rows into LEVEL1.MAP and the scroll phase
mid-tile. `test_the_prescroll_staging_is_the_originals_own_work` pins that the replay touched
nothing outside the ring and the 0x163fe..0x16432 band of scroll globals, and
`test_the_prescroll_really_scrolled` that it did something.

**Two things pinned by CONTRACT COVERAGE, not by game coverage**, each with a case that says so.

(1) An ODD scroll phase, which the game cannot produce — the phase is seeded 0x1e, stepped +2 and
masked to 0x1f, and the only other writer (`restart_level_at_checkpoint` @ 0x14bb6) is fed from five
shipped checkpoint tables whose every phase field is even. It separates THREE things nothing else
does. `tile_split_row_table`'s odd entries do not sum to TILE_BAND_ROWS (index 1 is (0, 6)), so the
tile band's `lea -1264(a2),a2` — applied to the cursor THE TWO HALVES LEFT, not to the band's top —
is only a fixed +16 a column while the pair sums to 8; the reconstruction had the fixed +16 until a
review caught it, and `test_render_frame_at_an_odd_scroll_phase` is what would have. And an odd
phase moves the overlay repaint's last row start to 167 or 169, which is where
`TILE_REPAIR_BOTTOM_CLIP_FROM_Y`'s two neighbours 0xa6 and 0xa9 stop agreeing with 0xa8;
`test_render_frame_repaints_a_full_grid` sweeps both.

(2) A screen base OFF the 0x500 grid, which is the only thing that separates the ring reseat's
`ring_base + 0x1f900` from `base + 0x1f900` — every base the game can hold is `ring_base + k*0x500`
and the step subtracts exactly one, so the pointer lands ON the limit and never below it. See
`test_render_frame_reseats_a_screen_base_below_the_ring`.

**One arm the game's own data cannot reach.** Twelve of the bank's 256 records (38-40, 42-46, 48,
49, 141 and 152) carry a hit box and NO bitmap: their `rows - 1` word is -1, so a blit would `dbf`
65,536 rows straight off the image. The game never publishes one of those ids into a display record
and the blitters are never entered with that count; the frame fuzz excludes them by id, and
`test_the_bitmapless_records_are_exactly_the_ones_the_fuzz_excludes` re-derives the list from the
bank so the exclusion cannot go stale.

**The under-budget wait runs through the SCHEDULED WRITE model**, not left unpinned. `render_frame`
spins on `vbl_tick` until the level-4 handler has counted the third VBL, and nothing inside this
program moves that counter — so the reconstruction reads it through `sched_poll16` at the original's
own re-read PC (0x1479c) and `test_render_frame_waits_out_the_rest_of_its_frame_budget` supplies the
handler's store from an external agent, exactly as `test_hud.py` does for the two ACIA waits. Two
details are this routine's: the compare is a LONG and the kit has only `sched_poll8`/`sched_poll16`,
so the loop is `sched_poll16`'s shape one width up — one poll an iteration for the clock, then a
full-width read — which loses that wrapper's CAP and nothing else; and the gate at 0x14786 reads the
same counter at its own PC and is deliberately NOT a poll. Without those cases the budget of 3 would
be pinned only from above: a budget of 2 takes the same arm at a tick of 3 and is invisible
(measured).

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x14446` | `render_frame` | 1306 | ✅ verified | 71 whole-frame cases on the prescrolled level: the prescroll short-circuit, an empty list, a pass-A sprite at nine x (both clip ladders and one x past each), a pass-B sprite at the 0xf0/0xf1 pair that separates its threshold from pass A's, eight vertical clips including y = 0xc7 and a class-3 sprite one row short of vanishing, all five active-byte boundaries, eight scroll phases (every distinct `tile_split_row_table` pair and the wrap that steps `map_row_ptr`) plus three ODD ones, the record's own draw offset, three scheduled VBL waits, all four ring indices, the seam at three bases the game really reaches — two inside its window and the third exactly ON its limit, which does NOT copy, the ring reseat, a full repair grid at seven phases, the map's own overlay tiles under a sprite (with each of the two span conditions switched off in turn, and a sprite clipped off the left edge whose cell index goes NEGATIVE), the band's masked path at all three split shapes and on either cell's overlay alone, a five-record restore replay over a RANDOMISED ring, and a 24-case sharded fuzz of five real sprites at random positions. Attribution is the randomised-ring case, not `poison=True`: the poison pass inverts `vbl_tick` (always written as 0, so poisoned to -1, which sends both cores into a wait nothing can end) and the four screen pointers, which steer the run rather than record it |
| `0x153b2` | `sprite_blit_w16` | 86 | ✅ verified | all 16 shifts over the game's own record 163, one row, the bank's own single-row record 47, and a share of the 96-case sharded fuzz over random pixel data. Poison. Mutations: the 0xffff0000 mask preload, the source group count, the gate bit position, the 160-byte row step and carrying the current group instead of the previous are each red |
| `0x15408` | `sprite_blit_w32` | 156 | ✅ verified | as above, over record 17 |
| `0x154a4` | `sprite_blit_w48` | 226 | ✅ verified | as above, over record 68 |
| `0x15586` | `sprite_blit_w64` | 296 | ✅ verified | as above, over record 71 — the bank's tallest, 64 rows |
| `0x14dda` | `sprite_blit_w16_clip_left` | 22 + 122 shared | ✅ verified | its one rung at the edge and one pixel inside it, and one pixel past — where nothing is drawn and the caller's restore cursor is rewound six bytes, which is a REGISTER answer the byte diff cannot see and the case reads out of `info["regs"]["a5"]`. Plus a share of the 96-case clip fuzz. The body from 0x14e1e is shared with 0x14df0 |
| `0x14e98` | `sprite_blit_w32_clip_left` | 40 + 210 shared | ✅ verified | as above, two rungs. Mutation: the second rung's -0x20 -> -0x18 is red |
| `0x14fd8` | `sprite_blit_w48_clip_left` | 58 + 298 shared | ✅ verified | as above, three rungs |
| `0x15188` | `sprite_blit_w64_clip_left` | 74 + 386 shared | ✅ verified | as above, four rungs; poison over a partly gated blit |
| `0x14df0` | `sprite_blit_w16_clip_right` | 46 | ✅ verified | both rungs one pixel and one group inside each edge, the abort past the last, and the rung that rewrites the pending restore record's class to 4. Mutation: dropping that rewrite, and moving it onto the OFFSET word, are both red |
| `0x14ec0` | `sprite_blit_w32_clip_right` | 70 | ✅ verified | three rungs, TWO of which narrow the restore record (to class 0 and to class 4). Mutation: making the middle rung leave the record alone is red |
| `0x15012` | `sprite_blit_w48_clip_right` | 76 | ✅ verified | four rungs, NONE of which narrows the restore — the bug above. Mutation: giving it the override its narrower siblings have is red |
| `0x151d2` | `sprite_blit_w64_clip_right` | 94 | ✅ verified | five rungs, no override |
| `0x14d58` | `restore_blit_w16` | 18 | ✅ verified | four row counts through `restore_blit_tbl` INDEX 4 — the entry `../notes/gameplay.md` says nothing reaches — and through `render_frame`'s own replay |
| `0x14d6a` | `restore_blit_w32` | 22 | ✅ verified | four row counts, 0 and 63 among them |
| `0x14d80` | `restore_blit_w48` | 26 | ✅ verified | as above. Mutation: 6 longwords a row -> 5 is red |
| `0x14d9a` | `restore_blit_w64` | 30 | ✅ verified | as above |
| `0x14db8` | `restore_blit_w80` | 34 | ✅ verified | as above, plus poison — a copy that copied nothing leaves the canary standing |
| `0x14d0a` | `tile_blit_overlay_masked` | 78 | ✅ verified | four row counts over pseudo-random base and overlay tiles, where the colour-0 keep mask differs in every word (a test applied per LONGWORD rather than per word fails), and one 32-row case over the game's own HSC banks with poison, where the mask is nearly all ones and a dropped AND would still look almost right. Mutations: not inverting the keep mask, and dropping the base longword, are both red |
| `0x156ae` | `scroll_wrap_copy_1280` | 162 | ✅ verified | 320 bytes into a seeded destination, with poison. Mutation: 79 longwords instead of 80 is red |

**Mutations tried against this section**, each from a green baseline with `build/` cleared and the
candidate relinked (`docs/agent-playbook.md` §10) — ONE consolidated sweep, so the figures are
measured together rather than carried: **68 tried, 66 red**. The four survivors below are
**equivalent mutants or unfalsifiable ones, not coverage holes** — the last two were added by the fix
wave rather than by the sweep, and each says which of the two it is:

| survivor | why no input can separate it |
|---|---|
| `TILE_REPAIR_PHASE_WRAP` 8 -> 9 | the constant is consulted only when a repaint row STARTS past y = 0xa8, and the two spellings differ only at `scroll_fine == 8` — the one phase whose last row starts exactly ON 168, so the branch is never taken there. No poke of any other global moves that row-start series. The neighbour 12 IS red |
| the tile band's two halves skipped on `== 0` instead of the `subq.b`/`bmi` BYTE sign | the two differ only for a split count of 0x81..0xff, and the only source of a count is `tile_split_row_table`, which is DATA in the .PRG holding 0..8. Transcribed as the byte test anyway; a case would have to fabricate a table the program does not contain |
| the overlay repaint's bottom clip given a `bmi` guard the original does not have | the difference is only ever a 65,535-ROW PASS, and no case can run one: 65,535 rows x 160 bytes is 10 MB of stores past a 1 MiB image, which the oracle drops on the floor and the candidate writes off the end of its buffer. `src/sprite.c` spells the unguarded `dbf` because that is the instruction, and this row is the honest form of "no case separates it" — the SIGNED half of the same arithmetic (`cmpi.w #$8 / blt`) IS separated, by `test_render_frame_repaints_at_a_NEGATIVE_scroll_phase`. The scroll phase the game itself holds is 0..0x1f, where neither half can fire |
| `advance_scroll`'s FIRST store of `map_row_ptr` dropped (`wr32(A_map_row_ptr, be32(A_map_row_ptr_reset))` @ 0x147dc) | the store is OVERWRITTEN BY THE NEXT LINE. 0x147da is a `nop` where the bound test used to be, so the store it guarded always runs and the stepped cursor always lands on top of it two instructions later — no reader can be interposed, because there is no instruction between them. Both stores are spelt out in `src/sprite.c` because both really execute; only the second is ever read, so the first cannot be pinned by anything and `A_map_row_ptr_reset` is a constant this reconstruction CARRIES UNVERIFIED. Its value is pinned only as a byte of the post-load fixture, and the one routine that reads it observably (`restart_level_at_checkpoint` @ 0x14b9a) is the player slice's, not this one's |

**Four mutations that survived an earlier sweep and do NOT belong above**, because the argument that
excused them was the wrong shape. `TILE_REPAIR_BOTTOM_CLIP_FROM_Y` 0xa8 -> 0xa9 and -> 0xa6 were
called equivalent on "row starts are even"; an odd phase moves the last start to 169 and 167 and
they disagree there. `RENDER_FRAME_VBL_BUDGET` 3 -> 2 was pinned only from above until a case
entered the wait at BUDGET - 1. And the ring reseat's two spellings needed a base off the 0x500
grid. In every one of the four the excuse was "the game cannot produce that input" — which is a
reason to LABEL a case contract coverage, not a reason to skip writing it.

## Verified — entity (39)

Wave 1's entity slice: the per-frame movers, the display-list publishers, the big object's
hide and depth passes, the power-up items and the frame/animation counters. `include/entity.h`
carries the FROZEN 58-byte record — every field tagged `pinned by <test>` or
`names.txt, unpinned` — which the player, weapons and spawn slices port against.

NO SEAMS. Both of this slice's calls into another subsystem are made for real and diffed through:
`sfx_play_2` @ 0x121e6 (the sound slice) out of `sprite_hitbox_test`, and `score_add_1000` @ 0x10b8c
(the hud slice) out of `item_drop_if_formation_cleared`'s bonus arm. Every routine here therefore
reaches its own `rts`, with the score digits and the sound module's own state inside the difference.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x11654` | `count_game_frame` | 8 | ✅ verified | the longword increment at six counter values including the 0xffffffff wrap, which a word increment would carry into the high half instead of dropping |
| `0x119fc` | `anim_frame_ids_update` | 134 | ✅ verified | ten frame-counter values, each over six SEEDED five-byte tables so a phase read one bit wide cannot agree with a repeated shipped id; plus eight counters over the game's own tables. Mutation: `ANIM_PHASE_MASK_3` 3 -> 2 and `ANIM_FRAME_TABLE_OFFSET` 1 -> 0 both red |
| `0x12e9e` | `entity_move` | 144 | ✅ verified | both modes. Script mode: five (dx, dy) pairs including 0x8000 through a word add that wraps; five countdowns including 0 (which wraps to 0xffff rather than stepping) and the step at exactly 1; three cursors; the 999 terminator. Death mode: all three `entity_path_tbl_ptrs` tables at four cursors over the game's own frame words, the negative-word end with and without the kind-4 has-dropped reset, and five kinds through the bomb drop. 640-case sharded fuzz over both modes. Poison on every arm that writes |
| `0x12f2e` | `enemy_bomb_drop` | 150 | ✅ verified | every position of the first free display record, 0..15 plus a full list — INCLUDING slot 15, which the original can never use (the scan cursor is bumped on both arms and tested before the write). The bug is reproduced and pinned: a fixed version is red. Four register positions; the `st 46(a0)` pinned as a BYTE against a record whose low half is seeded |
| `0x12e54` | `entities_move_group4` | 16 | ✅ verified | all eight turret groups over the staged world |
| `0x12e82` | `entities_move_one_group` | 6 | ✅ verified | all three pair entries — `movea.l (a6),a0` with no post-increment, so a four-slot walk reads past the entry |
| `0x12e22` | `entities_move_groups_extra` | 50 | ✅ verified | the five x-groups over the staged world |
| `0x12e64` | `entities_move_bigobj` | 30 | ✅ verified | the three pair objects with distinct velocities, including the third — which the original reaches as `lea $5a960,a0` rather than through the table. Mutation: that address moved to the neighbouring slot is red |
| `0x12e88` | `entities_move_bigobj_parts` | 22 | ✅ verified | the big object's four parts over the staged world |
| `0x12d5c` | `entities_move_all` | 198 | ✅ verified | all 91 slots over a world the ORIGINAL spawned (6,000 `spawn_script_step` calls against level 1's script, 28 live slots), plus a case that pins the a-group ORDER: two dying bombers in a2 and a3 take display records 0 and 1 in the order the groups are walked, so the a0, a1, a3, a2 sequence is red under an address-order walk |
| `0x1184e` | `enemy_bombs_move` | 44 | ✅ verified | eight y values around the signed 0xc8 retire test including the word wrap, over sixteen records half of them active; and the unconditional frame store, which a version that wrote the frame only to live records fails |
| `0x1187a` | `items_move_all` | 40 | ✅ verified | all sixteen combinations of the four items being live, so each of the three different step routines runs alone and beside the others; 320-case sharded fuzz |
| `0x118a2` | `item_drop_step` | 26 | ✅ verified | five y values around the retire test x three active words. NEW NAME (`item_drop_step`, since merged into ../names.txt): 0x118a2 is reached only by `items_move_all`'s tail branch and Ghidra had left it unnamed |
| `0x118bc` | `item_fall_step` | 30 | ✅ verified | six longword lifetimes including 0 (which goes to -1 and retires), 0x80000000 (already negative) and 0xffffffff, x two active words — the sign test after the decrement, which a zero test would get wrong on exactly those |
| `0x118da` | `item_path_step` | 66 | ✅ verified | five cursors including the terminator over the game's OWN `item_flight_path`, x three y values around the retire test; the terminator REWINDS rather than retiring |
| `0x1191c` | `items_publish` | 224 | ✅ verified | all sixteen live combinations, with the three cycling frame ids and the four display records seeded away from what the routine writes; pins the weapon/extra/life/bomb order, the literal 0xa1 for the bonus item and the bomb's pass-A active byte. 320-case sharded fuzz |
| `0x11698` | `sprite_hitbox_test` | 120 | ✅ verified | the WHOLE routine, sound module and awarded counter included — it calls the sound slice's verified `sfx_play_2` and falls into `item_pickup_award`. 144 item positions one step either side of every edge of both boxes, including the 0x10-square's own far edge; the draw offset and the box offset driven separately, which a candidate reading one field for both would pass without; five player frames including 0x80, which pins the sprite-bank index as unsigned. 320-case sharded fuzz over unrestricted words |
| `0x1165c` | `items_pickup_check` | 180 | ✅ verified | the whole routine. All eight combinations of the three items being live, run once with the player over them and once well away, so the weapon-then-bomb-then-life order and the early stop on the first pickup are both exercised |
| `0x11714` | `item_pickup_award` | 72 | ✅ verified | reached both as its own entry (five kinds x nine counter values) and by falling out of `sprite_hitbox_test`. Pins that the three caps are spelt three DIFFERENT ways: weapon and bomb stop on `beq` (exactly at the limit) and lives on a signed `bgt` (settling one higher) — a candidate that read all three the same way is red. NEW NAME (`item_pickup_award`), proposed by this slice and since merged into ../names.txt |
| `0x121fe` | `item_drop_if_formation_cleared` | 126 | ✅ verified | THE WHOLE ROUTINE, its `bsr score_add_1000` into the hud slice's `abcd` chain included. One survivor at each of the seven formation positions plus none, x four kinds, over a score whose middle BCD byte is 0x99 so the award carries; the `st 8(a0)` and `st $176c2` pinned as BYTES against seeded low halves. The 68000 X FLAG is an argument on the bonus arm and an answer on all four — `test_the_bonus_arm_threads_the_X_flag_through_the_score_chain` drives it both ways through `abi.extend_call_pokes` (borrowing D7, since D0 carries the drop's x) and compares the flag the routine leaves against the oracle's |
| `0x12cc8` | `difficulty_apply_fire_rates` | 144 | ✅ verified | SLICE [0x12cc8, 0x12d58) — the routine has no `rts`, it falls into `start_level` through a `bra.w`. All twelve descriptors seeded away from the values written, so a skipped descriptor differs rather than matching the shipped table. Mutations: a dropped descriptor and each of the four constants are red |
| `0x136a2` | `entity_publish_group_facing` | 96 | ✅ verified | all sixteen combinations of the four slots being alive or dying; the live frame (base + facing) against the dying frame (base + offset); four descriptor death offsets including 0x7fff/0x8000 at coordinates that wrap. 320-case sharded fuzz |
| `0x137f4` | `entity_publish_group_plain` | 68 | ✅ verified | all sixteen combinations of the four slots being hidden under the big object — the only publisher that consults that flag, and it CLEARS the record rather than skipping it; seven draw-layer words including 0xff00 and 0x00ff, which pin the active byte as the LOW half (../names.txt's 0x59984 comment has it backwards); six frame sums including 0x100 + 0x20, which pin the byte truncation |
| `0x1387a` | `entity_publish_anim` | 110 | ✅ verified | the frame-bump latch x the firing flag x three timer values; four animation periods x three timers, which pin the reload from +22 (ENTITY_HIT_POINTS's second role); the dying arm, which skips the animation entirely and leaves the timer standing; the inactive clear |
| `0x138e8` | `entity_publish_group_offset` | 82 | ✅ verified | all sixteen alive/dying combinations, with the death offset taken from the ENTITY's own +24/+26 rather than from a descriptor — a mutation that read +22/+24 instead is red. 320-case sharded fuzz |
| `0x13992` | `entity_publish_group_last` | 82 | ✅ verified | five dying masks over SEVEN slots, with the display run seeded so a four-slot walk leaves the last three records visibly untouched |
| `0x13702` | `entity_publish_group_a4` | 98 | ✅ verified | all sixteen alive/dying combinations over `entity_group_a4` under `enemy_desc_14` — which is the group the `lea`s name and NOT the big object the old name claimed. The correction is merged: ../names.txt calls it `entity_publish_group_a4` and so does the C |
| `0x13634` | `entities_publish_facing_groups` | 110 | ✅ verified | over the staged world, on its own so a pass that wrote another's display run is not masked |
| `0x13764` | `entities_publish_bigobj_group` | 16 | ✅ verified | likewise |
| `0x13774` | `entities_publish_plain_groups` | 128 | ✅ verified | likewise — and this is the pass whose two display runs are NOT contiguous (the turret barrel records sit between them); a single-progression version is red |
| `0x13838` | `entities_publish_anim_groups` | 66 | ✅ verified | likewise |
| `0x1393a` | `entities_publish_last_groups` | 88 | ✅ verified | over the staged world, plus a case with all four 7-slot groups populated and DYING and the four descriptors' death offsets seeded distinct — the shipped descriptors 00..03 all carry the same (10, 12), so a swapped group/descriptor pairing is invisible over the game's own data and that case is what makes it red |
| `0x1361c` | `entities_publish_all` | 24 | ✅ verified | the whole pass over the staged world, poisoned |
| `0x102de` | `bigobj_extra_parts_publish` | 48 | ✅ verified | five values of part 0's +22 around the 999 marker x two active words; the three stamps land on the FRAME bytes of records 1..3 and a version that started at record 0 is red |
| `0x1179a` | `entity_hide_test` | 90 | ✅ verified | 35 probe positions one step either side of every edge of the 0x40 box with the 0x0e offset in place; all sixteen subsets of the four parts overlapping, which pins that THE CLEAR IS INSIDE THE WALK (a clear-after-the-loop version is red); the dying-part exit, which clears as a word where the hide sets one byte. 320-case sharded fuzz |
| `0x11784` | `entity_hide_under_bigobj_group` | 22 | ✅ verified | four live masks over a group of four |
| `0x1175c` | `entity_hide_under_bigobj` | 40 | ✅ verified | the pass over all eight turret groups seeded, which pins that only the FIRST FOUR are tested — the seed's high byte is deliberately not 0xff, because with 0xff00 an eight-group walk writes the same byte and the mutation survives (measured) |
| `0x11820` | `bigobj_depth_test` | 46 | ✅ verified | five y offsets around the 0x0e probe x all sixteen live masks; pins that the clear is AFTER the loop here, the opposite of entity_hide_test — moving it inside is red. 320-case fuzz |
| `0x117f4` | `bigobj_overlap_depth_update` | 44 | ✅ verified | four combinations of parts 0 and 1 being live, with parts 2 and 3 and the other three x-groups seeded — pins that only two pairings are tested, and which two |

**Mutations tried against this section.** The porting wave ran its own sweep and reported 65
mutations with no survivors after five coverage holes were closed; that figure is the agent's and is
not re-derivable from the tree, so what is written here is what the FIX WAVE re-measured — eight
mutations, each applied on its own from a green 3,229-test baseline with `build/*.so` deleted and
`__pycache__` swept (`docs/agent-playbook.md` §10), each **red**, and each naming the failure count
it produced. Re-run them rather than quoting them.

| mutation | result | killed by |
|---|---|---|
| `ENEMY_BOMB_SLOTS` 16 -> 15 | red | 13 cases — the slot sweep that includes the sixteenth, which the original can never use |
| `ENEMY_BOMB_DY` 2 -> 1 | red | 81 cases, the item and bomb fuzz among them |
| `ENTITY_RETIRE_Y` 0xc8 -> 0xc7 | red | 3 cases — the y values one step either side of the retire test |
| `ITEM_EXTRA_FALL_FRAMES` 0x32 -> 0x31 | red | 11 cases of the item-drop sweep |
| the bomber's `ENTITY_HAS_DROPPED` guard dropped, so it drops every frame | red | 10 cases — `test_a_bomber_drops_exactly_once` and the move fuzz |
| `publish_frame` writing the frame as a WORD instead of a byte | red | 118 cases across every publisher |
| the pickup's lives cap read as the `beq` its two siblings use, instead of the signed `bgt` | red | 9 cases of `test_item_pickup_award_caps_each_counter_its_own_way` |
| `item_drop_if_formation_cleared`'s bonus `bsr score_add_1000` dropped | red | 10 cases — the score seam this wave joined, killed by the BOMB column of `test_item_drop_needs_every_slot_of_the_formation_gone` and by `test_the_bonus_arm_threads_the_X_flag_through_the_score_chain` |

## Verified — player (29)

Wave 2's player slice: the plane's input, its two scripted flights, its bank, its death sequence,
the five weapon patterns, the two collision passes that kill it, and the level-flow pair that ends
and restarts a stage. `include/player.h` carries the record's remaining fields and the mode byte's
six values; `A_player`, `PLAYER_MODE`, `PLAYER_X/Y/FRAME`, `A_lives`, `A_bombs`, `A_player_hit` and
`A_dl_player_shadow` are still spelt in `include/hud.h` and `include/entity.h`, which borrowed them
before this subsystem existed — the loans are theirs to give back and the rows are below.

THREE SEAMS, all of them into routines that never return. (1) The collision hit arm ends `bra.w
score_add_200`, whose `abcd` chain adds the X flag the sound module's `sfx_start` left two
instructions earlier — an input this routine cannot know — so the hit is diffed at that branch.
(2) The death sequence's "lives left" arm unwinds its caller into `restart_level_at_checkpoint`, of
which only the head is reconstructed, so it stops at that routine's entry. (3) The level advance
unwinds the same way into the frame loop. Both paths into `game_over_hiscore_check` are NOT seams:
that routine is the hud slice's and is CALLED, so they are diffed through the whole hall-of-fame walk
to its own re-entry into `main`.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10f26` | `player_vs_entities` | 74 | ✅ verified | the pass over the GAME'S own five slot tables with the one live entity in each group in turn plus none — so a pass that stopped after the four `bsr`s is red on the last case and one that used the a4 box for all five is red on the first four. Both early exits (the "HSC" cheat and game-over mode) over a world that would otherwise kill the plane on slot 0 |
| `0x10f70` | `player_vs_entities_group_a4` | 24 | ✅ verified | NEW NAME, proposed by this slice and since merged into ../names.txt: the five-`move.w`-and-`bra` sibling reached only by `player_vs_entities`' tail. The live entity in each of its FOUR slots plus none, and its box's four edges as hand-worked absolute literals. Mutation: `ENTITY_BOX_A4_W` 0x39 -> 0x3a red |
| `0x10f88` | `player_vs_entities_group` | 24 | ✅ verified | the live entity in each of its SEVEN slots plus none, and its box's four edges as hand-worked literals — driven through THIS entry rather than the shared loop's, because the loop takes the box in registers and a case entering there would drive the test's copy of a constant instead of the reconstruction's. Mutations: `ENTITY_BOX_W` 0x1b -> 0x1c, `ENTITY_BOX_H` 0x17 -> 0x18 and `ENTITY_BOX_DX` 0x11 -> 0x10 all red |
| `0x10fa0` | `player_vs_entity_group_test` | 120 | ✅ verified | SLICE [0x10fa0, 0x11018) — the hit arm ends `bra.w score_add_200` (above). One entity stepped one pixel either side of every edge of the box in BOTH axes, which is four separate `bgt`s; the active and dying word tests including 0xff00; the already-dying exit. REPRODUCES A BUG and pins it: the y test overwrites the box WIDTH in D1 with the box HEIGHT from D6 before using it, so the first slot whose x span meets the player narrows the box for every slot after it — a version that kept the width kills a second entity and is red. 80-case sharded fuzz over unrestricted words |
| `0x1101c` | `player_vs_enemy_bullets` | 184 | ✅ verified | the plane's own sprite box against sixteen aimed shots: one bullet stepped either side of each of the four edges the test compares, seven player frames including 0x80 (which pins the frame byte as an UNSIGNED bank index) and 0x7f, the walk driven with the hit in slot 0, 3, 6, 9, 12 and 15 plus none — the SIXTEENTH written as a literal, since deriving it from the slot count made a fifteen-slot walk agree. The already-dying arm, which runs the whole walk and then refuses WITHOUT clearing the bullet. 80-case sharded fuzz |
| `0x124ae` | `level_progress_check` | 218 | ✅ verified | SLICE — the level-advance arm ends `addq.l #4,a7 / bra.w $15758` and is diffed there; every other arm returns. Over a level the ORIGINAL started (`start_level` @ 0x11440 run under the oracle), so the end-of-level and boss triggers are the game's own 0x12f2 and 0x128e; one either side of each. Both gates (a plane on the landing script, and `game_over_flag`) over a scroll past both triggers. The advance from every level, and all eight combinations of the three one-shot loop flags — which is what pins that the game restarts at level 1, then 2, then 3, and only then at 0 |
| `0x139e4` | `takeoff_script_reset` | 30 | ✅ verified | over the shipped template with the live script and its cursor dirtied first, and over a seeded template with a SIXTH distinctive word behind it — so a copy of six leaves it in the script and one of four leaves the dirt in word five. Poisoned. Mutation: `SCRIPT_TEMPLATE_WORDS` 5 -> 4 red |
| `0x13a02` | `landing_script_reset` | 30 | ✅ verified | the same two cases against its own template and cursor |
| `0x13a20` | `player_script_step` | 394 | ✅ verified | all three arms plus the five modes that fall through. Take-off: three cursors including the terminator x four shadow timers, over the game's own script, plus a script whose first two countdowns are already 0 — which pins that a retired record is replaced WITHIN the same call. Landing: three cursors x six (timer, bombs) pairs including `bombs = 0xffff` (the signed guard) x two shadow timers, and the terminator arm. Fly-off: five x's and three y's around the landing point x three hover timers, plus the fire-enable latch clear on the target in both axes |
| `0x13baa` | `player_bank_recentre` | 44 | ✅ verified | four turning values x seven banks including 0x8000 and 0xffff, which pin the compare as SIGNED. Poisoned |
| `0x13bd6` | `player_death_sequence_step` | 192 | ✅ verified | every frame of the shipped death table over display records seeded away from what it writes — the plane published ON TOP and its shadow's record CLEARED. The three terminal arms: "a life left" and the infinite-lives cheat both unwind into `restart_level_at_checkpoint` (diffed at its entry) including `lives = 0x8000`, which steps to 0x7fff and is NON-ZERO — a sign test would get it wrong; the last life, which reloads both counters out of `const_words_0123`; and the expired banner, diffed through `game_over_hiscore_check` to its own re-entry into `main` |
| `0x13c96` | `player_publish` | 124 | ✅ verified | five modes x three shadow offsets including 0xffff, with a plane frame of 0xfd so the shadow's `addi.b #$7` WRAPS rather than climbing out of the bank; the dying arm's hand-over and the game-over arm's banner. The bank table is seeded, because the shipped one repeats ids and a frame read one step off would agree with it |
| `0x13d12` | `player_frame_from_bank` | 18 | ✅ verified | all thirteen bank indices over a seeded table whose bytes are all distinct |
| `0x13d24` | `player_reset_to_start` | 56 | ✅ verified | four banks over a template and a record both seeded away from what it writes, which pins that the routine WRITES THE TEMPLATE on the way past — the bank's frame is stamped into 0x1909c and only then copied out of it, so the template carries the last reset's bank from then on. Plus the shipped template untouched |
| `0x13d5c` | `bomb_drop` | 68 | ✅ verified | five bomb counts x the cheat, which pins the count test as SIGNED (0xffff refuses) and that the cheat skips the test AND the decrement; five (falling, exploding) pairs including 0xff00; four x values through the `addi.w #$c` that wraps in sixteen bits |
| `0x13da0` | `player_move_up` | 16 | ✅ verified | ten y values around the limit including negatives and 0x8000 — the test is `blt` on a SIGNED word and a GATE, not a clamp: a plane already past the limit is left where it is. ../names.txt's "y clamped to 0x0b..0xbb" is wrong twice over (correction filed) |
| `0x13db0` | `player_move_down` | 18 | ✅ verified | eight y values around 0xba, the other end's `bgt` — which lets every negative y through |
| `0x13dc2` | `player_move_left` | 38 | ✅ verified | five x values x all thirteen banks, over the shipped table and over a seeded one. Two gates and neither is a clamp: `tst.w / beq / bmi` refuses zero AND any negative x, and the bank steps down only while the byte BEFORE it in `player_bank_frames` is positive. Mutation: probing the byte AT the index instead is red |
| `0x13de8` | `player_move_right` | 42 | ✅ verified | six x values x all thirteen banks, likewise, against the table's other sentinel |
| `0x13e12` | `player_fire` | 60 | ✅ verified | three fire-held values x slots free/full x three `sfx_active` values — which pins that this call is GATED on the module reporting no effect running, unlike all six `sfx_play_*` wrappers, so the fire sound is the one effect in the game that yields. The debug-overlay arm is driven too, with the flag poked and a checkpoint at the fall-through into `console_show_message`: it is UNREACHABLE in the shipped game (`debug_overlay_flag` is written by no instruction in the image) and an arm no case executes is an arm no mutation can kill |
| `0x13e4e` | `player_shot_slot_alloc` | 110 | ✅ verified | all eight combinations of the three busy flags, including all three taken — the only arm that RAISES `shot_slots_full` instead of clearing it |
| `0x13ebc` | `player_fire_by_weapon_level` | 36 | ✅ verified | all five levels x the "JH" cheat, which OVERWRITES `weapon_level` rather than only steering the dispatch. The pattern address is read out of the image and dispatched by value, as `src/hud.c`'s cheat table is. Mutation: `WEAPON_LEVEL_MAX` 4 -> 3 red |
| `0x13ee0` | `fire_pattern_level0` | 64 | ✅ verified | five player positions, three of which make the muzzle arithmetic WRAP, over a slot whose five bullets are SEEDED — zeroed records could not tell "wrote 0" from "wrote nothing". Part of a 120-case sharded fuzz over the five patterns |
| `0x13f20` | `fire_pattern_level1` | 82 | ✅ verified | the same, plus the QUIRK case: the pattern clears the fourth bullet's state WORD and sets its high byte but NEVER writes its dx, so that bullet flies with whatever the previous shot in the same slot left. Reproduced; a version that zeroed it is red |
| `0x13f72` | `fire_pattern_level2` | 104 | ✅ verified | the same, with its own running-sum x chain — and it DOES write the fourth bullet's dx, after the state store rather than before |
| `0x13fda` | `fire_pattern_level3` | 114 | ✅ verified | the same; this one leaves the fourth bullet's dx alone |
| `0x1404c` | `fire_pattern_level4` | 128 | ✅ verified | the full five-way fan, whose last two bullets share one x |
| `0x14354` | `read_player_input` | 242 | ✅ verified | all sixteen stick states x the button; the button through to the bullets at every weapon level; both bomb buttons alone and together; the input lock; `use_keyboard_flag` both ways, which pins that it moves ONE test (the "nothing held" short-circuit) because the direction tests re-read `joy1_state` regardless. The PAUSE key is a SCHEDULED wait — it spins on a byte only the ACIA interrupt writes, so the reconstruction polls through `sched_poll8` and the harness compares its polls against the oracle's arrivals at four release points; nothing else can see the iteration count. The ABORT key does not return: it throws away this routine's register save and its caller's return address, and is diffed through `game_over_hiscore_check` to `main`. 100-case sharded fuzz with the two system keys masked out |
| `0x14aac` | `restart_level_at_checkpoint` | 118 | ✅ verified | SLICE [0x14aac, 0x14b22) — from `st level_just_started` to the `bsr clear_actor_arrays` that follows it; the entry instruction 0x14aa8 is a `bsr set_palette_black`, so the slice starts after it. Both of those calls are the init subsystem's and both are VERIFIED now, so the span is where this slice's own work is rather than where the port ran out; what still has no row is the routine's TAIL, which ends `bra.w $1575c` back to the frame loop's top instead of returning. Every level's table x every record, driven at the record's own scroll position (where the `blt` either takes it or steps past it), plus one either side of record 0's — which is where the walk either stops or runs off the FRONT of the table, since it has no floor — plus a scroll past the tables' own 0x2710 sentinel, which is the only thing that says where the scan STARTS. Also over the machine `start_level` itself left. FINDING: the routine clears `key_last_scancode` (0x17781) and NOT `key_bits` beside it, so a held pause or abort key really does survive a restart — which is what `level_just_started` has to gate off |

**Mutations tried against this slice**, each from a green baseline with `build/*.so` removed and the
candidate relinked (`docs/agent-playbook.md` §10). Fifty in all, and after the four holes below were
closed every one is RED:

| mutation | killed by |
|---|---|
| the twelve geometry constants (`PLAYER_Y_MIN`, `PLAYER_Y_MAX`, `PLAYER_X_MAX`, `PLAYER_STEP_PIXELS`, `PLAYER_BANK_CENTRE`, `SHADOW_FRAME_OFFSET`, `SHADOW_OFFSET_AIRBORNE`, `SHADOW_FRAME_ON_DECK`, `FLYOFF_TARGET_X`, `FLYOFF_TARGET_Y`, `FLYOFF_HOVER_FRAMES`, `BOMB_DROP_X_OFFSET`) each moved by one | the edge case that brackets it, by name |
| the six timers and steps (`TAKEOFF_SHADOW_PERIOD`, `LANDING_SHADOW_PERIOD`, `BOMB_CASH_PERIOD`, `DEATH_SINK_PIXELS`, `DEATH_FRAME_BYTES`, `BULLET_MUZZLE_DY`) | likewise |
| the eight table constants (`SCRIPT_TEMPLATE_WORDS`, `SCRIPT_STEP_BYTES`, `SCRIPT_STEP_FRAME`, `CHECKPOINT_REC_BYTES`, `CHECKPOINT_SCROLL_BACK`, `LEVELS`, `LEVEL_LOOP_2_START`, `LIVES_AFTER_GAME_OVER`, `WEAPON_LEVEL_MAX`, `BOMBS_MIN_TO_DROP`, `SCORE_AWARD_3000`, `SFX_PLAYER_FIRE`) | likewise |
| `move_left` probing the bank frame AT the index instead of before it | `test_move_left_gates_on_x_and_on_the_bank_table_sentinel` over the SEEDED table |
| the fourth bullet's dx written after all (the quirk repaired) | `test_fire_pattern_leaves_the_fourth_bullets_dx_alone` — and only because the slot's five records are seeded |
| the D1 clobber removed (the collision box keeps its width) | `test_group_test_narrows_the_box_after_the_first_x_overlap`, written for it |
| `player_fire` dropping the `sfx_active` gate; `read_player_input` skipping the pause spin; `JOY_LEFT_BIT`/`JOY_RIGHT_BIT` swapped; `KEY_BOMB_BIT` 5 -> 4 | the input battery |
| **FOUR SURVIVORS, since closed.** `ENTITY_BOX_W`/`_H`/`_DX`/`_A4_W` moved by one | SURVIVED: every box probe DERIVED its position from the constant, so the mutant moved the probe with the box, and the shared-loop entry takes the box in registers besides. Closed by hand-worked ABSOLUTE probes driven through `player_vs_entities_group` and `_a4`, which load the constants themselves |
| `ENEMY_BULLET_HIT_OFFSET` 0x10 -> 0xf and `ENEMY_BULLET_SLOTS` 16 -> 15 | SURVIVED for TWO reasons, both defects in the battery: `_sprite_box` read the player's sprite record out of `harness.BASE_IMAGE`, where the sprite bank is not loaded and every box word is ZERO; and the enemy bullet records were built with the PLAYER bullet's layout, putting the active word at +6 instead of +8, so all sixteen were inactive and the routine was verified entirely on its skip path. Closed by `enemy_bullet_record`, a `post_load_image` box and an assertion that the box is not degenerate |
| `LANDING_SHADOW_PERIOD` 2 -> 3 | SURVIVED: every landing case seeded the shadow timer AT the period, so it decremented to 1 and the reload arm was never reached. Closed by a second parametrised value of 0 |
| `CHECKPOINT_SCAN_FROM` 0x26 -> 0x20 | SURVIVED: below the tables' 0x2710 sentinel every start point from record 5 upwards finds the same record. Closed by a scroll position PAST the sentinel |

## Verified — weapons (89)

Every projectile in the game and everything that spawns one. Two things about this section are worth
reading before its rows: the HIT HANDLERS are verified through their dispatchers rather than at their
own entry addresses, and half of them thread the 68000 X FLAG into the score chain.

**Why the handlers have no entry of their own.** Both dispatchers read a handler ADDRESS out of a
constant table indexed by the descriptor's +22, so poking that one word selects any of the nineteen
entries — `test_weapons.py`'s `test_every_bullet_hit_handler_over_every_hit_point_edge` and its blast
twin sweep all nineteen against nine hit-point values each, which reaches every one of the
twenty-three handlers AND the dispatch that finds it. The same argument covers the 25 spawn stubs
(`test_spawn_script_step_dispatches_every_type`, all 26 types — the twenty-sixth is `spawn_item_bomb`,
which has an entry and a row of its own) and the five firing groups (`enemies_fire_all`'s own
unrolled call list). The five COMMON BODIES those stubs share are verified BOTH ways: through the
dispatch, and at their own entry addresses by `test_the_three_four_slot_spawn_bodies`,
`test_spawn_single_common`, `test_spawn_squadron_common` and
`test_a_spawn_over_a_dirty_arena_shows_which_fields_it_leaves`.

**The X flag is an argument.** `score_add_bcd` opens with an `abcd`, which ADDS X (`include/hud.h`),
so what a hit awards depends on a condition code the handler inherited. Every step is a plain 68000
rule — `Scc`/`move`/`clr`/`tst`/`cmp`/`movem`/`lea` leave X alone, `addi`/`subi` set it, `lsl` sets it
to the last bit shifted out, and the four sfx wrappers pass it through because the module entry
@ 0x58df0 writes no condition code — and `test_the_drop_position_is_a_word_add_whose_carry_reaches_the_score`
is the case that makes the inheritance visible: a kill at a y whose `addi.w #$11` carries scores one
point more than a kill at a y that does not.

| Addr | Name | Cases | State | What the verification covered |
|---|---|---|---|---|
| `0x115fc` | `clear_object_list` | 5 | ✅ verified | FILED HERE, NOT UNDER `init`: the only array it touches is `A_enemy_bullets` and its only caller in ported code is `bomb_blast_step`. Four array lengths, and the case that shows the walk tests EVERY word rather than each record's active field — a bullet whose x happened to be 999 ends the clear early. Poison on the four length cases |
| `0x10e7c` | `bomb_fall_step` | 13 | ✅ verified | five cursors along a poked fall path including its 999, five start rows over the word wrap (0x7ffd + 4 is negative), the not-falling short-circuit, and both arms that arm the blast — the terminator and `bomb_exploding` already set. Poison |
| `0x10ee2` | `bomb_publish` | 4 | ✅ verified | all four (falling, exploding) combinations over a dirty display record, with a frame of 0x1234 to show the word-to-byte narrowing. Poison |
| `0x10c8c` | `bomb_blast_step` | 24 | ✅ verified | all sixteen step values including `BLAST_LAST_STEP` and one past it, four impact positions over the word wrap, and the not-exploding short-circuit. Covers `clear_object_list` and `sfx_play_10` firing on EVERY frame of the blast, not only the first. **D0 IS AN INPUT**: `move.w $176ec,d0 / lsl.w #3,d0 / adda.l d0,a0` loads only the low word and adds all 32 bits, so the caller's high word picks the offset row. The core takes it; three cases drive it, and the two with a non-zero high word FAILED against a core that zero-extended, which is how the dependency was found |
| `0x10d20` | `bomb_blast_publish` | 2 | ✅ verified | exploding and not, over four dirty records. Poison |
| `0x11a82` | `bomb_blast_vs_entities` | 1 | ✅ verified | the frame loop's own call over the STAGED WORLD (`spawn_script_step` run 3,000 times against level 1's script under the oracle), with the blast's four points spread across the playfield — 22 descriptors x 4 points x each group's entities |
| `0x11b90` | `bomb_blast_vs_entities_if_active` | 2 | ✅ verified | exploding and not; the guard is also what sets the D7 the group pass counts its four points with |
| `0x11bb6` | `bomb_blast_vs_entity_groups` | 345 | ✅ verified | the 19 x 8 handler/hit-point sweep, 72 box-edge positions against a box whose near and far corners are both offset, a 120-case sharded fuzz over random entity positions, boxes and blast points DRIVEN THROUGH A HANDLER THAT WRITES (see the mutation table: over the immune entry the fuzz stored nothing, so a mis-computed box was invisible), and the case that shows a blast point does NOT stop the entity walk (four stacked entities take four hits from one point, unlike a bullet). `make guarded` clean: the sprite-record index is a computed address |
| `0x11c76` | `blast_hit_score200` | via 345 | ✅ verified | table entry 0. Kill, 200 points, sfx 6 |
| `0x11c84` | `blast_hit_score200_drop_item_a` | via 345 | ✅ verified | table entry 1, plus the 24-case item sweep: three item kinds x cleared and not. Its `addi.w #$11` pair is what leaves X for the award |
| `0x11caa` | `blast_hit_score200_drop_item_b` | via 345 | ✅ verified | table entry 2 — byte-identical to entry 1's body |
| `0x11cce` | `blast_hit_score200_drop_item_c` | via 345 | ✅ verified | table entry 3 — likewise |
| `0x11cf2` | `blast_hit_score200_if_visible` | via 345 | ✅ verified | table entries 4..11, and the arm where an entity hidden under the big object refuses the hit |
| `0x11d06` | `blast_hit_immune` | via 345 | ✅ verified | table entries 13 and 14: a bare `rts`, driven as the box fuzz's handler so that the BOX is what those cases are about |
| `0x11d08` | `blast_hit_damage4_a` | via 345 | ✅ verified | table entry 15. Four damage, 5000 for the kill, the one-shot frame bump at +40, and the survive path that awards 50 ONLY on the arm that starts the enemy firing back — unlike its bullet twin, which awards on all three |
| `0x11d40` | `blast_hit_damage4_b` | via 345 | ✅ verified | table entry 16. Four damage, 200 for the kill, and the arm that moves the base frame on by 12 — whose `addi.w #$c` re-sets X before the award |
| `0x11d7c` | `blast_hit_damage5` | via 345 | ✅ verified | table entry 17. It subtracts FIVE, not four (`subi.w #$5` @ 0x11d7c) — which is why ../names.txt now calls it `blast_hit_damage5`, the rename this slice proposed and the merge took |
| `0x11dae` | `blast_hit_score100` | via 345 | ✅ verified | table entry 18 |
| `0x11dba` | `blast_hit_damage6` | via 345 | ✅ verified | table entry 12. It subtracts SIX, its kill test is `bmi` ALONE (so zero hit points leaves the entity alive and awards 50), and its refusal arm is a bare `rts` — where the BULLET twin at 0x1214a awards 50. Both were found by this sweep going red |
| `0x11de6` | `player_bullets_vs_entities` | 1 | ✅ verified | the frame loop's own call over the staged world, all three shots live |
| `0x11e04` | `player_bullets_vs_entities_group` | 1 | ✅ verified | one shot against all 22 descriptors, staged world |
| `0x11f0c` | `player_bullet_vs_entity_groups` | 353 | ✅ verified | the 19 x 9 handler/hit-point sweep, the 24-case item sweep, five drop-position carries, 24 box-edge positions, the eight (active, dying, hidden) combinations, the case that shows one bullet stops at the FIRST entity it hits, and a 120-case sharded box fuzz. `make guarded` clean |
| `0x11fca` | `bullet_hit_score200` | via 353 | ✅ verified | table entry 0 |
| `0x11fdc` | `bullet_hit_score200_drop_item_a` | via 353 | ✅ verified | table entry 1, and the item sweep. It is one of the six handlers that `bsr` into `item_drop_if_formation_cleared` @ 0x121fe (entity) and then `bsr` the score chain again — so the X the drop's own bonus arm leaves is what this handler's award then inherits, which `drop_item_and_score` threads and the drop-position carry case makes visible |
| `0x12004` | `bullet_hit_score200_drop_item_b` | via 353 | ✅ verified | table entry 2 |
| `0x1202c` | `bullet_hit_score200_drop_item_c` | via 353 | ✅ verified | table entry 3 |
| `0x12054` | `bullet_hit_two_stage_100_then_50` | via 353 | ✅ verified | table entries 4..11, and BOTH its stages: the first bullet marks +28 and awards 100, the second kills and awards 50. ../names.txt's old name covered only the second stage; the merge took this slice's rename |
| `0x12084` | `bullet_hit_immune` | via 353 | ✅ verified | table entries 13 and 14 |
| `0x12086` | `bullet_hit_damage_a` | via 353 | ✅ verified | table entry 15. REPRODUCES A BUG: the kill test is `cmpi.w #$1` AFTER the subtract, so the enemy dies with one hit point left, not with none. It also awards 50 on every survive arm, where its blast twin awards on one |
| `0x120c6` | `bullet_hit_damage_b` | via 353 | ✅ verified | table entry 16, with the base-frame bump and the arm that returns without an award |
| `0x12104` | `bullet_hit_damage_c` | via 353 | ✅ verified | table entry 17 |
| `0x1213a` | `bullet_hit_score100` | via 353 | ✅ verified | table entry 18 |
| `0x1214a` | `bullet_hit_damage_d` | via 353 | ✅ verified | table entry 12: one damage, 500 for the kill, and 50 even when it refuses the hit outright |
| `0x1227c` | `muzzle_flash_publish_all` | 2 | ✅ verified | over the staged world, and over a world with ENTITY_FIRING set in every slot of the four groups it walks — the staged world's entities never fire, so the interesting arm needs the flag |
| `0x122c0` | `muzzle_flash_publish_pair` | 12 | ✅ verified | the eight (active, dying, firing) combinations and four positions over the word wrap. CONFIRMS the `# ctx` name: it reads the descriptor's +28/+30/+32/+34 and publishes two records. Poison |
| `0x12348` | `muzzle_flash_publish_group` | 3 | ✅ verified | three frame offsets, which is what selects between the bumped glyph with no drop and the plain glyph six rows down — the `subi.w #$6` / `addi.w #$6` pair the original spells as one branch writing zero. Poison |
| `0x125bc` | `enemy_bullets_publish` | 4 | ✅ verified | four array lengths up to 12, live and free slots alternating, stopping at the 999. Poison |
| `0x12602` | `enemies_fire_all` | 17 | ✅ verified | the abort at three `player_hit` values, four reload boundaries over the staged world, and ten positions on the firing window's edges. Covers all four group routines and the ONE shared bullet cursor that is never reset, so a frame that fills the array drops every later shot |
| `0x12856` | `enemies_fire_abort_if_player_hit` | via 17 | ✅ verified | NOT reconstructible standalone and not a nop: `addq.l #4,a7` discards its own return address so the `rts` returns out of `enemies_fire_all`. Ported as that routine's guard, and covered by its three `player_hit` cases. The old name `enemies_fire_nop` said the opposite; the merge took this slice's rename |
| `0x127ba` | `enemies_fire_group_a` | via 17 | ✅ verified | one shot, and the `subi.w #$20,d0` that shifts the SHARED aim point left for the rest of the frame |
| `0x1273a` | `enemies_fire_group_b` | via 17 | ✅ verified | three shots at (aim), (aim - 0x20) and (aim + 0x20) with only the first guarded, and the only window that admits an entity down to row -16 — which the window-edge cases separate from its three siblings' |
| `0x12810` | `enemies_fire_group_c` | via 17 | ✅ verified | one shot at a SHIFTED COPY of the aim point, so the shared aim is left alone |
| `0x1286c` | `enemies_fire_group_d` | via 17 | ✅ verified | the turrets': three extra gates (hidden, wrecked, mid-rotation) and the 0x19 recoil applied to the slot the spawn left the cursor on — including when the spawn failed and that slot is the array's own sentinel |
| `0x128ce` | `enemy_bullet_spawn_aimed` | 199 | ✅ verified | four free-slot positions plus the array-full refusal, three module-busy values for the one site in the game that tests it, and a 192-case sharded fuzz over the aim arithmetic: the arithmetic shifts, the signed 21-column grid index and the signed velocity index. The sweep is BOUNDED to the window its four callers guard widened by a screen, because an unbounded one indexes the lookup outside the program — which `make guarded` faults on rather than reading as data |
| `0x12964` | `enemy_bullets_move` | 89 | ✅ verified | nine clip-box edges, one pixel inside and one outside each, plus an 80-case sharded fuzz over random positions, steps and active words. Poison |
| `0x129b2` | `turrets_aim_all` | 1 | ✅ verified | the eight turret groups and the five facing groups over the staged world |
| `0x12a50` | `turrets_aim_group` | 4 | ✅ verified | the unconditional form: it aims a dead turret too |
| `0x12a34` | `turrets_aim_group_active` | 4 | ✅ verified | ...and the form that skips one, over the same four (active, dying) combinations — which is the whole difference between them |
| `0x12c04` | `turret_aim_step` | 256 | ✅ verified | 14 facings x 8 desired bearings, which reaches both wraps (11 -> 0 and 0 -> 11) and BOTH already-aimed arms (+6 and -6, the same bearing read from either side), plus a 144-case sharded fuzz over the 23-column grid index. `make guarded` clean |
| `0x12a60` | `turrets_publish_all` | 1 | ✅ verified | the eight groups over the staged world, four off each pair of offset tables |
| `0x12b40` | `turret_publish_group` | 56 | ✅ verified | eight (state, hidden) combinations — including the two states that publish NOTHING and leave the record as the last frame left it — and 48 (body frame, facing) pairs over the game's own barrel tables |
| `0x12fc4` | `spawn_script_step` | 93 | ✅ verified | all 26 handler types through the game's own dispatch table, 20 cases over the shipped formation tables, five trigger comparisons, the script's 0xa3a1 end, 12 weapon-offer fallbacks, four bomb-offer ones (the `st` writes only the flag's HIGH byte, so a low byte already set makes the second offer fall back), and 25 records of the five shipped level scripts |
| `0x13044` | `spawn_item_bomb` | 4 | ✅ verified | four positions over the word wrap. Poison |
| `0x130aa` | `spawn_formation_common` | 5 | ✅ verified | four retired-slot patterns from none to all four, plus a run over an arena pre-filled with 0xff — which is what makes the fields a body does NOT write visible |
| `0x131a4` | `spawn_single_common` | 2 | ✅ verified | with and without its one slot retired. The only body that writes ENTITY_ANIM_TIMER, from the same descriptor word as the hit points |
| `0x132dc` | `spawn_bigobj_parts_common` | 5 | ✅ verified | four retired-slot patterns at its own entry (`test_the_three_four_slot_spawn_bodies`) plus the dirty-arena case, and through the dispatch as types 14/15/16/19/25. Pins what separates it from its two prologue twins: draw layer 1, fire countdown 10, `clr.w` on +24, hit points from the descriptor — and then the OVERWRITE of +24/+26 with the descriptor's +18/+20 death offset |
| `0x1343e` | `spawn_turret_common` | 5 | ✅ verified | the same four patterns plus the dirty arena, and through the dispatch as types 04..11. The dirty-arena case is what makes its two ABSENCES visible: it writes no hit points and no firing flag, so a turret keeps whatever its previous life left in +22 and +38 |
| `0x13544` | `spawn_squadron_common` | 3 | ✅ verified | three retired-slot patterns over a SEVEN-slot formation at its own entry, and through the dispatch as types 00..03. Its records are seven (dx, dy) pairs, seven longword script offsets and one script base at +28/+56 rather than +16/+32 — the slot count 7 -> 4 mutation below is red in 31 cases |
| `0x1351c` | `spawn_stub_type00` | via 93 | ✅ verified | reached through the dispatch table by its own type index: squadron, off `formation_tbl_squadron` — its body (0x13544, `spawn_squadron_common`, with a row of its own below) is the SEVEN-slot one, whose formation records are seven positions, seven script offsets and one base |
| `0x13526` | `spawn_stub_type01` | via 93 | ✅ verified | reached through the dispatch table by its own type index: squadron |
| `0x13530` | `spawn_stub_type02` | via 93 | ✅ verified | reached through the dispatch table by its own type index: squadron |
| `0x1353a` | `spawn_stub_type03` | via 93 | ✅ verified | reached through the dispatch table by its own type index: squadron |
| `0x133fe` | `spawn_stub_type04` | via 93 | ✅ verified | reached through the dispatch table by its own type index: turret, off `formation_tbl_turret_b` |
| `0x1340e` | `spawn_stub_type05` | via 93 | ✅ verified | reached through the dispatch table by its own type index: turret, off `formation_tbl_turret_b` |
| `0x1341e` | `spawn_stub_type06` | via 93 | ✅ verified | reached through the dispatch table by its own type index: turret, off `formation_tbl_turret_b` |
| `0x1342e` | `spawn_stub_type07` | via 93 | ✅ verified | reached through the dispatch table by its own type index: turret, off `formation_tbl_turret_b` |
| `0x133be` | `spawn_stub_type08` | via 93 | ✅ verified | reached through the dispatch table by its own type index: turret, off `formation_tbl_turret_a` — the body (0x1343e) writes no hit points and no firing flag, pinned by the dirty-arena case |
| `0x133ce` | `spawn_stub_type09` | via 93 | ✅ verified | reached through the dispatch table by its own type index: turret, off `formation_tbl_turret_a` |
| `0x133de` | `spawn_stub_type10` | via 93 | ✅ verified | reached through the dispatch table by its own type index: turret, off `formation_tbl_turret_a` |
| `0x133ee` | `spawn_stub_type11` | via 93 | ✅ verified | reached through the dispatch table by its own type index: turret, off `formation_tbl_turret_a` |
| `0x13190` | `spawn_stub_type12` | via 93 | ✅ verified | reached through the dispatch table by its own type index: single, off `enemy_desc_10` — a one-slot body with no formation table at all |
| `0x1319a` | `spawn_stub_type13` | via 93 | ✅ verified | reached through the dispatch table by its own type index: single, off `enemy_desc_11` |
| `0x1329c` | `spawn_stub_type14` | via 93 | ✅ verified | reached through the dispatch table by its own type index: big-object parts — the body (0x132dc) overwrites +24/+26 with the descriptor's death offset |
| `0x1328c` | `spawn_stub_type15` | via 93 | ✅ verified | reached through the dispatch table by its own type index: big-object parts |
| `0x132ac` | `spawn_stub_type16` | via 93 | ✅ verified | reached through the dispatch table by its own type index: big-object parts |
| `0x1305a` | `spawn_stub_type17` | via 93 | ✅ verified | reached through the dispatch table by its own type index: plain formation, off `formation_tbl_a` |
| `0x1306a` | `spawn_stub_type18` | via 93 | ✅ verified | reached through the dispatch table by its own type index: plain formation, off `formation_tbl_a` |
| `0x132cc` | `spawn_stub_type19` | via 93 | ✅ verified | reached through the dispatch table by its own type index: big-object parts, off `formation_tbl_parts_c` |
| `0x1307a` | `spawn_stub_type20` | via 93 | ✅ verified | reached through the dispatch table by its own type index: plain formation, off `formation_tbl_b` |
| `0x1308a` | `spawn_stub_type21` | via 93 | ✅ verified | reached through the dispatch table by its own type index: plain formation, off `formation_tbl_b` |
| `0x1309a` | `spawn_stub_type22` | via 93 | ✅ verified | reached through the dispatch table by its own type index: plain formation, off `formation_tbl_b` |
| `0x13186` | `spawn_stub_type24` | via 93 | ✅ verified | reached through the dispatch table by its own type index: single, off `enemy_desc_18` |
| `0x132bc` | `spawn_stub_type25` | via 93 | ✅ verified | reached through the dispatch table by its own type index: big-object parts, off `formation_tbl_parts_b` |
| `0x140cc` | `player_bullets_move_all` | 1 | ✅ verified | the three shots at once |
| `0x140ea` | `player_bullets_move_group` | 117 | ✅ verified | three states x seven y values across the retire edge (`> -8`, not `>= -8`), plus a 96-case sharded fuzz. REPRODUCES A QUIRK: only the hit state short-circuits the step, so a FREE slot is moved too and its dead coordinates drift |
| `0x14118` | `player_bullets_publish_all` | 1 | ✅ verified | the three runs of five records |
| `0x14148` | `player_bullets_publish_group` | 10 | ✅ verified | unnamed in Ghidra (`FUN_00014148`) until this slice's proposal was merged. Five state values x the "GCC" cheat flag both ways, over dirty records: the free arm clears, the hit arm draws the impact frame AND frees the slot, and the flag swaps 0x7f for 0xe4. Poison |
| `0x141b4` | `player_shot_slots_release` | 1 | ✅ verified | the three busy flags, one of them held by a live bullet |
| `0x141e4` | `player_shot_slot_release_if_empty` | 6 | ✅ verified | a live bullet at each of the five positions and at none. Poison |

**Mutations, eighteen of them, each applied on its own from a green baseline with
`rm -f build/*.so` before the run** (`docs/agent-playbook.md` §10). The first sweep of these was a
LIE and is worth recording: it passed `--timeout=600` to a pytest with no such plugin, so every
mutant exited non-zero at argument parsing and every one was reported killed. The numbers below are
from the re-run without it, and every row names the failure count it produced.

| mutation | result | killed by |
|---|---|---|
| `bomb_blast_step` zero-extending D0 instead of keeping its high word | red | 2 cases — and the ZERO-EXTENDING version was the reconstruction until those cases were written |
| `PLAYER_BULLET_DY` 0x13 -> 0x12 in BOTH the header and the battery's mirror | red | 19 cases — `test_player_bullet_step` and its fuzz |
| `BLAST_DAMAGE_5` 5 -> 4, so the handler would deal the four its old name claimed | red | 8 cases of the blast handler sweep |
| `BULLET_KILL_AT_HIT_POINTS` 1 -> 0, i.e. the off-by-one "fixed" | red | 2 cases — the sweep's hit-point 1 and 2 columns against table entry 15 |
| `AIM_LUT_ROW_STRIDE` 0x15 -> 0x14 in BOTH the header and the mirror | red | 9 cases of the aim fuzz |
| `TURRET_LUT_ROW_STRIDE` 0x17 -> 0x16, likewise | red | 7 cases of the turret lookup fuzz |
| `hit_dispatch` indexing by `ENEMY_DESC_HANDLER` (+16) instead of `ENEMY_DESC_KIND` (+22) | red | 267 cases — which is how ../names.txt's comment on 0x19534 was found wrong |
| `spawn_arm_slot` writing `clr.w` on +24 where the original writes `st` | red | 37 cases, `test_a_spawn_over_a_dirty_arena_shows_which_fields_it_leaves` among them |
| `enemies_fire_group_a` shifting a COPY of the aim point instead of the shared one | red | 6 cases — the firing-window edges and a staged-world reload |
| `spawn_squadron_common`'s slot count 7 -> 4 | red | 31 cases of the type dispatch |
| `player_bullets_move_group` skipping a FREE slot as well as a hit one | red | 11 cases — the quirk is load-bearing |
| `clear_object_list` testing each record's ACTIVE word instead of every word | red | 5 cases |
| `enemy_bullet_spawn_aimed` leaving its cursor where it started | red | 9 cases |
| `muzzle_flash_publish_group` dropping the six-row shift | red | 2 cases |
| `turret_aim_step` comparing the bearing against +6 only, not -6 as well | red | 5 cases |
| `bomb_fall_step` adding the path's dy to the LIVE row instead of the start row | red | 9 cases |
| the blast box's `span_x` read as `HIT_W` alone | red **after a fix** | SURVIVED the first sweep, and the two reasons are worth keeping: `_collision_pokes` gave every case `hit_dx == draw_dx`, which makes the subtraction a no-op, and the box FUZZ was driven through the IMMUNE handler, so a mis-computed box produced no store to differ. The helper now takes both corner pairs and the fuzz runs through a handler that writes; 9 cases kill it |
| the blast box's `near_dy` read as `HIT_DY` alone | red **after the same fix** | SURVIVED for the same two reasons and was only tried because its sibling had; 6 cases kill it now. Two survivors from one blind spot is what a single mutation would have hidden |

**One thing here is unfalsifiable and is recorded rather than papered over.** `HIT_DISPATCH_EXTEND` is
the X flag a dispatcher hands its handler — `lsl.w #2`'s bit 14 on the handler index — and it is zero
for every one of the nineteen indices either table can serve. An index wide enough to make it 1 would
read a table entry 0x10000 bytes past the table and outside the program, so no case can drive the
other value. It is a constant in `src/weapons.c` for that reason, with the argument beside it.

## Verified — hud (41)

The score, the hall of fame, the readouts they feed and the console leftovers. Every routine here is
arithmetic over the image — the six-byte records they publish are read by `render_frame` a frame
later — so the plain byte diff is the check except where a routine answers only in registers, which
`test/abi.py`'s three stub shapes make visible.

**Mutation sweep: 56 mutations, 54 red, 2 EQUIVALENT and none surviving as a coverage hole.** Each
was applied to `src/hud.c` from a green baseline with `build/*.so` deleted and relinked
(`docs/agent-playbook.md` §10), and reverted. Five needed a case that did not exist and got one:

| mutation | what closed it |
|---|---|
| `abcd`'s wrap test `> 0x99` -> `> 0x9a` | `test_the_abcd_wrap_boundary` — the sum has to land exactly on 0x9a, which needs low nibbles summing past 9 with high nibbles summing to 0x80. NO award in the game's table can produce it (their bytes are 0x00 and 0x01), so it took driving `score_add_bcd` with an addend of the case's own |
| the rank walk given a floor (`muls.w`'s sign extension dropped) | `test_the_rank_walk_goes_NEGATIVE_when_what_is_below_the_table_loses_too` — a score that beats row 0 stops at rank 0 whichever way the extension goes; the two only diverge when the walk goes to rank -1, which needs the script bytes below the table replaced by glyphs the score also beats |
| `game_over_hiscore_check`'s `hard_mode` clear dropped | seeding `hard_mode` non-zero in every case of that section: the byte is zero in the post-load image, so the store was being compared against a zero it never had to write |
| the cheat matcher's off-by-one rewind CORRECTED to two | `test_the_rewind_bug_can_fire_a_cheat_the_name_does_not_spell` — one name in the whole glyph space separates them, found by walking both matchers over every name built from the table's own letters |
| the arm spin's 5001 iterations cut to one | routing that spin through `sched_poll8` and giving every cheat case a schedule, so the count is compared poll-for-arrival. Without it the count is invisible: nothing can change `key_bits` while the candidate runs |
| `debug_show_counters` printing the raw map pointer instead of the difference | a reset value whose LOW WORD is non-zero (`DEBUG_MAP_RESET`). `format_5_digits` masks to 16 bits, so the old 0x20000 made both readings print the same five digits |

The two survivors are EQUIVALENT MUTATIONS — the same program, not a hole:

* **the lives clamp's `>=` weakened to `>`.** They differ only at `lives == 7`, where the clamp
  stores seven over seven. `cmp.w #$7,d7 / blt` in the original takes the clamp at exactly seven and
  the store is a no-op, so no input can tell them apart.
* **`game_over_hiscore_check`'s `move.b #$f0,5(a1)` @ 0x1073e dropped.** The very next instruction
  calls `bcd3_to_digits`, which rewrites all six digit glyphs including that one, on every path and
  unconditionally. The store is dead by construction; what a case CAN pin is its consequence, which
  is that a tying score takes no row (`test_the_tie_the_dead_store_was_meant_to_win_is_lost`).

| Addr | Name | Cases | State | What the verification covered |
|---|---|---|---|---|
| `0x10698` | `build_text_display_list` | 51 | ✅ verified | the compiler's five opcodes plus the glyph default, in one script and separately; the 0x06 INDENT opcode at six values of the word it reads out of ABSOLUTE ADDRESS 0x40 (the vector page, not this program's data — reproduced, not repaired); the byte-wide header moves, driven with a caller high byte of 0xdead_ff00 so a `move.w` reading of them is red; a newline resetting the column to 0 rather than to the script's start. 40-case sharded fuzz over random opcode streams. A1/D1/D2 and the script cursor come back through `abi.register_dump_pokes` because the routine walks A0 itself |
| `0x106f2` | `hiscore_show_entry_screen` | 3 | ✅ verified | SLICE [0x106f2, 0x10916) — the routine ends `bra.w hiscore_name_entry`, which is deferred. Both arms of `name_entry_done`, so the second script really is compiled on to the END of the first: that chaining is what pins `build_text_display_list`'s returned cursors through memory |
| `0x10724` | `game_over_hiscore_check` | 39 | ✅ verified | SLICE [0x10724, 0x15754) — both arms re-enter `main` rather than returning. A score at and below the lowest row (a TIE loses); one award above each of the six shipped entries, so the walk stops at each rank and the right rows are pushed down; the walk running OFF THE BOTTOM at rank 0; and, with the script bytes below the table replaced by glyphs the score also beats, the walk going NEGATIVE — which is where `muls.w`'s sign extension is the difference between reading the front end's text and reading 1.4 MB past the image. 24-case sharded fuzz over random tables, including rows out of descending order. `hard_mode` is seeded non-zero in every case so its clearing store is not compared against a zero it never wrote |
| `0x108aa` | `hiscore_shift_entry_down` | 5 | ✅ verified | all five rows that can be shifted, over a table filled with a distinct byte per offset, poisoned — so the 13 bytes from +9 are pinned at both ends and the rank digit at +8 is pinned as NOT moving |
| `0x108c0` | `hiscore_reset_last_digit` | 1 | ✅ verified | all six rows over a canary-filled table, poisoned |
| `0x108f8` | `digits6_compare` | 64 | ✅ verified | the ALL-EQUAL run, which answers LOWER (the `dbf` falls into the same `move.w #$ffff,d0`) and is why a tie takes no row and awards no life; one digit apart at each of the six positions each way, with every LATER digit disagreeing the other way so a routine that kept walking answers differently; and the SIGNED compare, driven with 0x00 and 0x7f entry bytes against real digit glyphs — the case that decides `game_over_hiscore_check`'s walk off the table. 48-case sharded fuzz. D0/A5/A6 come back through `abi.register_call_pokes`, with D0 merged into a seeded caller high half |
| `0x10a02` | `hud_build_labels` | 1 | ✅ verified | the two caption records over a canary, poisoned — the whole routine is eight stores and a candidate making none of them would otherwise be compared against a zeroed display list |
| `0x10a2a` | `check_beat_hiscore` | 15 | ✅ verified | a higher and a lower digit at each of the six positions, and a tie; the flag seeded 0x0042 to pin `st` as a BYTE store into a word the readout reads whole |
| `0x10a50` | `hud_build_score_digits` | 6 | ✅ verified | five values of `hiscore_beaten` including 0x00ff and 0xff00 — it is tested as a WORD although `check_beat_hiscore` only ever writes its high byte, so a low byte alone switches the source |
| `0x10a90` | `hud_publish_digit_row` | 9 | ✅ verified | the sixth record's FORCED '0' (the row's own sixth glyph is never published, which is why every score ends in a zero); five columns including 0xfff8, where `addi.w` wraps rather than carrying into the caller's high half; two cases with a high half seeded in both coordinate registers |
| `0x10ab4` | `hud_blank_leading_zeros` | 4 | ✅ verified | four leading-zero pairs across the two readouts |
| `0x10ac8` | `hud_blank_leading_zeros_row` | 8 | ✅ verified | every count of leading zeros from 0 to 6, so the walk's stop at the first non-zero digit and its five-record limit are both driven — the sixth record, the forced '0', is never blanked |
| `0x10ae4` | `scores_bcd_to_chars` | 5 | ✅ verified | four score/hi-score pairs including nibbles above 9, plus a poisoned case over all twelve glyphs so a candidate converting only the score stays canary on six |
| `0x10b04` | `bcd3_to_digits` | 19 | ✅ verified | zero, 999999, 0xffffff and a 64-case sharded fuzz over arbitrary bytes — a nibble above 9 lands PAST '9' in the alphabet rather than being clamped, which is what `addi.b #$c5` does |
| `0x10b28` | `score_add_50` | 10 | ✅ verified | driven through `abi.extend_call_pokes`, so the 68000's X flag is an INPUT (the first `abcd` adds it) and the X the wrapper leaves is compared against the oracle's. From zero and from 999999 (the score WRAPS, it does not saturate), six carry-boundary scores, both X values, and its share of a 192-case sharded fuzz over random scores; attribution over the three score bytes |
| `0x10b3c` | `score_add_100` | 3 | ✅ verified | as `score_add_50`: both X values from zero, the 999999 wrap, and its share of the shared 192-case fuzz. Each wrapper differs only in the `lea` that picks its award, and each names the address ONE PAST its own three bytes |
| `0x10b50` | `score_add_200` | 3 | ✅ verified | likewise |
| `0x10b64` | `score_add_250` | 3 | ✅ verified | likewise |
| `0x10b78` | `score_add_500` | 3 | ✅ verified | likewise |
| `0x10b8c` | `score_add_1000` | 3 | ✅ verified | likewise — and the one wrapper another slice calls: `item_drop_if_formation_cleared` (0x121fe, entity) ends its bonus arm here, and is diffed through it |
| `0x10ba0` | `score_add_3000` | 3 | ✅ verified | likewise |
| `0x10bb4` | `score_add_5000` | 3 | ✅ verified | likewise |
| `0x10bd8` | `score_add_10000` | 4 | ✅ verified | likewise, plus attribution — the ninth wrapper is NOT contiguous with the other eight (0x10bc8 sits between them and is an unrelated level-2 hook) |
| `0x10bec` | `score_add_bcd` | 112 | ✅ verified | the leaf with an addend the case chose, which is what lets the ABCD WRAP BOUNDARY be driven at all: the seven byte pairs where the instruction's own thresholds are decided (0x99 exactly, 0xa0 exactly, and 0x9a — which is where a `> 0x99` and a `> 0x9a` differ) are unreachable through the nine fixed awards, whose addend bytes are 0x00 and 0x01. Both X values throughout, and a 96-case sharded fuzz with BOTH operands random over the whole byte range |
| `0x10d92` | `check_cheat_name` | 103 | ✅ verified | all five reachable names (`cheat_jml_crash` is deferred: it is a `jsr 0`); the arm spin driven through the SCHEDULED-WRITE model so its ITERATION COUNT is compared poll-for-arrival — the key arriving at reads 1, 2, 5000 and 5001, and never, which pins `move.w #$1388,d7` + `dbf` at 5001 passes and not 5000; four names that match nothing; the OFF-BY-ONE REWIND after two matched glyphs, including the one name that separates it from its correction (`J G C` with a fourth byte of 'C' fires the GCC cheat, found by walking both matchers over every name built from the table's own glyphs); the HSC handler's second-use arm. 80-case sharded fuzz weighted towards the table's letters |
| `0x10e30` | `cheat_hsc_invulnerable` | 3 | ✅ verified | both arms — the first use sets `invuln_flag`, a SECOND use sets `player_hit` instead and kills you — plus a 0xff flag, poisoned |
| `0x10e4c` | `cheat_kdj_infinite_lives` | 1 | ✅ verified | the one store, over a canary run covering all five cheat flags, poisoned — each handler writes 1 and not 0xff, and touches no neighbour |
| `0x10e56` | `cheat_jgl_infinite_bombs` | 1 | ✅ verified | likewise |
| `0x10e60` | `cheat_gcc_alt_glyph` | 1 | ✅ verified | likewise |
| `0x10e72` | `cheat_jh_max_weapon` | 1 | ✅ verified | likewise |
| `0x110d4` | `award_extra_life` | 29 | ✅ verified | TWO CHECKPOINT SHAPES, because the routine has two exits: an `rts` when nothing is awarded and a `bra.w sfx_play_2` (0x121e6) when something is, which is an EXIT and not a call — so every byte it writes is already written at the checkpoint and the sound trigger stays the sound subsystem's. Each of the seven thresholds as the first unclaimed one, at the threshold exactly (which does NOT award: an equal comparison answers lower), one award above and one below; every flag set; a score past several thresholds collecting exactly one life; five life counts including 0x7fff and 0xffff, which the word add takes negative and to zero |
| `0x11570` | `debug_print_word_binary` | 7 | ✅ verified | seven words including 0x8000 and 0xaaaa. `lsl.w` shifts the WORD, so a longword argument's high half never reaches the output — the OS event ledger is the only surface that can see any of it |
| `0x1159c` | `console_putc` | 5 | ✅ verified | five bytes including 0x1234, whose low byte alone is what Cconout receives |
| `0x115a8` | `clear_display_list` | 1 | ✅ verified | 0x177ce..0x17d07 with a guard record either side, poisoned |
| `0x115c2` | `clear_player_display_slots` | 1 | ✅ verified | the twelve bytes with a guard record either side, poisoned. RENAMED: 0x17cfc is `dl_player_shadow`, so this clears the PLAYER's two records and not the score's — ../names.txt took this slice's `clear_player_display_slots`, and the C follows it |
| `0x11616` | `score_reset` | 1 | ✅ verified | the three BCD bytes and the sixth digit glyph, over a canary — the other five glyphs are deliberately NOT reset, which a candidate that cleared the run would fail |
| `0x1162e` | `clear_3_bytes` | 1 | ✅ verified | three bytes with a guard byte either side |
| `0x123d8` | `hud_publish_bomb_and_life_icons` | 39 | ✅ verified | every bomb count 0..7 against three life counts; the SIGNED clamp at 7, 8, 0x100 and 0x7fff, with the clamped value written BACK into the game's own counter; the game-over mode, which clears the player's two records instead and returns before the life row, and six other modes; and BOTH OVERRUNS reproduced — the life loop has no `bmi` guard and its `dbf` runs the body first, so 0 lives publishes 65,536 records and a negative count escapes the clamp and does the same |
| `0x14960` | `debug_show_counters` | 5 | ✅ verified | SLICE [0x14960, 0x14996) — the original FALLS THROUGH into `console_show_message` without ever loading A6 with the string it patched, so what it prints is the caller's register and the slice ends at that fall-through. Five counter triples including a map advance of 0x10000, which `format_5_digits` masks away |
| `0x14996` | `console_show_message` | 8 | ✅ verified | the Setscreen and the four VT52 cursor bytes through the OS event ledger; four messages, whose terminator is a byte with BIT 7 SET and not a NUL; and the fire-release spin through the scheduled-write model at four release points, so the loop's iteration count is compared poll-for-arrival rather than only its memory |
| `0x14a76` | `format_5_digits` | 94 | ✅ verified | nine values at every digit count including zero (which writes no digits at all and leaves "00000"); four longwords, which `swap / clr.w / swap` masks to 16 bits before the first divide; 80-case sharded fuzz over the whole 32-bit range. A0's resting place and D0 come back through `abi.register_dump_pokes`, the routine walking A0 itself |

## Verified — irq (5)

Wave 3's interrupt slice: the level-4 vertical blank, the MFP channel-6 IKBD/MIDI ACIA handler and
its two joystick continuations, and the TOS joystick callback the ACIA handler displaced.

**AN INTERRUPT IS ENTERED BY THE 68000 AND LEAVES THROUGH `rte`,** so on the machine it runs on an
exception frame. Every one of these four balances its own pushes BEFORE that instruction, so the
frame is read by the `rte` alone — which is what lets each case enter at the routine's first
instruction and stop AT the `rte` without fabricating a frame. `acia_ikbd_isr` has FOUR `rte`s, one
per arm, and the case's declared ACIA byte is what picks the arm and therefore the checkpoint.

**THE INPUT IS OFF-IMAGE AND DECLARED.** The byte the 6850 hands over is `hw_read8(OS_HW_ACIA_DATA)`
against a `move.b $fffffc02,d1`, and the model serves it only to a case that declares it
(`hw_seed=`). The port is VOLATILE — a read pops the receive register — so one declaration is one
read, which is exactly what each of these three routines makes.

**SO IS HALF THE OUTPUT.** Every path ends `bclr #6,$fffffa11`, a READ-MODIFY-WRITE and not a store:
`hw_bclr8` is what puts it in the ordered hardware WRITE ledger and what keeps the other five
channels' in-service bits alive on a target build. Its POSITION in the routine is not observable off
target — see "Unpinned on target".

**THE VBL's CHAIN IS WHERE THE SLICE ENDS.** `vbl_handler` closes `jmp $1164e.l`, whose operand
`boot_init` fills from TOS's own $70. The model has no vector there, so the slice stops at the `jmp`
and the chain itself is a row in "Unpinned on target" — where it already was before this slice
landed. The counter's LONGWORD WRAP is driven anyway (0xffffffff + 1 = 0, unguarded), which is what
separates a 32-bit increment from a 16-bit one.

**THE ONE PLACE THE GAME'S OWN DATA PROVES THE LADDER RUNS WHOLE.** The eight watched scancodes are
compared in an unrolled ladder with no early exit, and the shipped table lists 0x00 TWICE (bit 3 and
bit 7) — so a received 0x00 moves two bits at once. That is game coverage, not a poked table.

**THE ACIA BYTE IS SWEPT EXHAUSTIVELY, and it used not to be.** The handler's whole input is one
byte, so 256 cases is the entire domain; what was there was a 96-draw random fuzz, which drew 78
DISTINCT bytes and left 178 of the 256 undriven (measured 2026-09-07 by replaying its own seeds).
`test_the_isr_over_every_byte_the_acia_can_hand_it` now runs 0..255, sharded four ways so `-n auto`
still spreads it, with the entry `key_bits` and scancode still randomised per byte.


**Mutations tried**, from a green baseline with a forced relink. One SURVIVED, and it is structural
rather than a coverage hole a case could close.

| mutation | result |
|---|---|
| the VBL counter incremented as a WORD | red — `test_the_vbl_counts_a_frame_and_ticks_the_sound_module`, at the wrap |
| the VBL counter not incremented at all | red — the same case |
| `vbl_handler` drops the module's `jsr 38(a0)` | red — the same case, through the image AND the PSG ledger |
| the two joystick packet headers swapped | red — `test_a_joystick_header_re_points_the_vector_at_its_continuation` |
| the make/break test reads the CLEARED bit instead of the original | red — `test_every_watched_scancode_moves_its_bit` |
| the raw scancode is not kept in `key_last_scancode` | red — the same case |
| `KEY_WATCH_SCANCODES` 8 -> 7 | red — the same case, at bit 3 |
| `acia_joy0_byte` stores into joystick 1 | red — `test_a_continuation_stores_its_stick_and_hands_the_vector_back` |
| a continuation never restores $118 | red — the same case, which is why its entry vector is swept |
| the joystick packet is read one byte early | red — `test_tos_joyvec_copies_the_packets_two_state_bytes` |
| the raw scancode store SKIPPED for one unwatched byte (0x42) | red — `test_the_isr_over_every_byte_the_acia_can_hand_it[2]`, and nothing else (1 failed / 3,552 passed). The random fuzz this replaced never drew 0x42, so the same mutant survived it — which is the measurement that made the sweep exhaustive |
| `MFP_ISRB_ACIA_BIT` 6 -> 0 | **SURVIVED the differential and cannot not**: `hw_bclr8` ledgers `0 & ~(1 << bit)`, which is 0 for every bit, so the write entry is `(0xfffa11, 1 byte, 0)` whatever bit is named — the ADDRESS is pinned by the ledger and the BIT by nothing. Closed by `test_the_end_of_interrupt_names_channel_six_at_every_rte_path`, which reads the `bclr` instruction word out of the loaded image at all four `rte` paths; `test_constants.py`'s mirror is the second link that ties the C define to it |
| the end-of-interrupt runs BEFORE the key ladder instead of after | **SURVIVED** — see "Unpinned on target": the hardware write ledger and the image diff are separate streams, so an off-image write cannot be ordered against image writes here |

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x11636` | `vbl_handler` | 24 | ✅ verified | SLICE [0x11636, 0x1164e) — the counter and the sound module's tick, at both machine speeds and over six entry counts including the longword wrap. One case runs it over a driver `music_start` has left with a tune RUNNING (staged by the module's own routine under the oracle), so the tick has a whole frame of music to do and the PSG's register stream is the second surface. Mutations: a word-wide increment, no increment at all and a dropped `jsr 38(a0)` are red |
| `0x141fa` | `tos_joyvec_handler` | 30 | ✅ verified | DEAD ON THE MACHINE and verifiable anyway: `acia_ikbd_isr` has taken the ACIA vector, so TOS's packet parser never calls it. Bytes 1 and 2 of a random three-byte packet into the two stick states, sharded, with a random byte 0 the callback must ignore; plus poison. Its `lea $1777e(pc),a1` loads an address nothing then uses |
| `0x14218` | `acia_ikbd_isr` | 244 | ✅ verified | All three arms: the two joystick packet HEADERS (each re-points $118 at its continuation and touches nothing else) and the KEY path, whose eight rungs are driven for every watched scancode, pressed and released, over three entry states of `key_bits` — the rungs are `bset`/`bclr`, so a reconstruction that assigned the byte would pass at 0x00 and fail at 0xff. Plus unwatched codes at both ends of the make range and a sharded fuzz over all 256 bytes. The two vector operands are read out of the loaded image. Mutations: swapped headers, a make/break test on the cleared bit, a dropped raw-scancode store and a seven-rung ladder are red |
| `0x1430c` | `acia_joy0_byte` | 36 | ✅ verified | The second byte of a joystick-0 report: store it, acknowledge the MFP, restore $118. 0xff is driven as a legitimate stick byte — the continuation does not decode, it stores, which is the whole reason the two-state machine exists — and the entry vector is swept over three values so that "restores" means something. Mutations: the wrong stick and a dropped restore are red |
| `0x14330` | `acia_joy1_byte` | 36 | ✅ verified | The same shape at `A_joy1_state`; the two routines differ in one address |

## Verified — sound (30)

**THE ROUTINES BELOW 0x58944 ARE NOT IN `../names.txt`, and that is not an omission.** Flying Shark's
whole audio path is a SECOND GEMDOS `.PRG` — `A\MODULE.BAK` — that the boot chain reads into the bss
and calls at `A_sound_module` (`include/globals.h`); it has its own Ghidra project
(`../ghidra_proj_module`), its own decompile (`../out/module_decomp.c`), its own listing
(`../out/module_dis.txt`) and its own name map, `../out/names_module.txt`, which is where every
`0x589xx`–`0x58exx` name in this section is spelt. So these rows cite MODULE names, and the
"Not reconstructed" accounting for `../names.txt` is unaffected by them: the only `fn` lines this
subsystem owns are the seven GAME-side wrappers at the bottom of the table, and all seven are here.

**What the verification rests on, once, rather than in thirty rows.** The driver's output is 13 or 14
YM2149 register writes a frame at `$ff8800`/`$ff8802`, which are OUTSIDE the memory image: a port
that pushed nothing at all would be byte-identical to a correct one. The kit's direct-PSG access
ledger is the surface that sees them (`tools/recreate_kit/TRAP_MODEL.md`, Phase 6) and
`differential` compares it on every case. The strongest shape available is therefore a whole track
in ONE oracle run, and `test_a_tune_plays_the_same_register_stream_for_frames` is it: each of the
five tunes for 240 frames at BOTH machine speeds, so the sequencer over three channels, the note
lengths, the instruments, the envelopes refilling, the arpeggios, the vibrato, the pitch slides, the
pattern changes and the mixer are all live at once over the game's own data, and the comparison is
the multi-frame register stream IN ORDER plus every byte of the driver's state at the end. The case
also asserts the stream's own length, so a run that silently got shorter cannot report green.

**The tempo is a hardware READ**, `btst #1,$ffff820a`, so every case that reaches the music half
declares that byte with `hw_seed=` (Phase 7) and runs at both settings. Serving the undeclared `0`
would be a 60 Hz machine — a fifth slower — agreed on by both sides, which is the `$ffff820a` defect
BuggyBoy shipped green. The driver never READS the chip, so no case needs a `psg_seed`; that is
checked rather than assumed, by `../tools/extract_audio.py`'s `vetted_psg_writes`.

`../tools/extract_audio.py` drives this same original through this same oracle to write
`../out/audio/manifest.tsv`; the frame counts that file measured are what these cases select (240
frames of a tune, 84 of an effect, the longest of which runs 80).

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x5896a` | `sound_vbl_tick` | 390 | ✅ verified | the entry the game calls once a frame, from `vbl_handler` and nowhere else. A tick with nothing playing (the flush is unconditional, so silence is a register stream and not an absence of one); seven ticks with a tune running at both machine speeds, which is what pins the 60 Hz divider dropping one frame in six; the divider entered at each of its phases INCLUDING zero, where `subq.b #1` wraps to 0xff and 255 more ticks run before one is dropped; all five tunes for 240 frames each at both speeds; all thirteen effects to their own end; an effect started over a running tune; `sound_stop` mid-track; the master volume over its whole range; and three sharded fuzz batteries. The envelope-shape latch — register 13, pushed only on the ticks its shadow byte is non-zero and zeroed by the push — is pinned by a case that COUNTS the pushes, since no image byte records it |
| `0x58af0` | `seqcmd_end_of_song` | 6 | ✅ verified | pattern command 0x88, and the one routine here that does not return to its caller: it overwrites `channel_sequencer_step`'s return address on the stack with 0x589d6 so the `rts` lands past the whole music update. Entered at the TICK for that reason (entering at the sequencer would rewrite the harness's own return address), with channels B and C armed with a note each so that "they did not get their sequencer step" is visible in the image, and with the noise shadow and all three periods left as the previous frame set them. Deleting the abandon reddens that one case and nothing else |
| `0x58af6` | `sound_stop` | 20 | ✅ verified | clears `music_active` and the three volume SHADOWS, so the chip only hears it on the following flush. Both arms: with an effect running (it does not touch `sfx_active`, so the effect plays on and the very next tick overwrites the channel-C volume just cleared) and without. Reached through `music_stop` as well, and mid-track between two ticks |
| `0x58b0a` | `seqcmd_next_pattern` | 32 | ✅ verified | pattern command 0x85, through the dispatch. Both arms of the sequence list: a live entry, and the 0x0000 terminator that RESTARTS the list at index 0 rather than ending it — which is how a tune loops, and is why `music_active` never goes clear for one. Also every frame of the five 240-frame tune runs, which is where the shipped lists are walked |
| `0x58b2a` | `seqcmd_tie` | 6 | ✅ verified | pattern command 0x8c, through the dispatch, plus the case that shows what it is FOR: a note whose predecessor was 0xff keeps the running volume envelope, and one whose predecessor was 0x00..0x7f does not. Both arms at the sign boundary |
| `0x58b30` | `seqcmd_set_transpose` | 6 | ✅ verified | pattern command 0x89 through the dispatch, and the transpose it sets is driven over the period-index cases (0, +12 and a negative) |
| `0x58b36` | `seqcmd_set_pitch_slide` | 14 | ✅ verified | pattern command 0x82 through the dispatch, two operands consumed in the original's order; the machine it arms is driven separately over delays 0/1/2 and steps 1/0x7f/0x80/0xff, which is what pins `ext.w` on the step and the ACCUMULATOR (not the step) reaching the period |
| `0x58b44` | `seqcmd_set_vibrato` | 22 | ✅ verified | pattern command 0x86 through the dispatch, two operands, and the limit stored as the depth DOUBLED as a byte; the sweep it arms is driven separately at both ends of its travel |
| `0x58b5a` | `seqcmd_portamento_down` | 4 | ✅ verified | pattern command 0x83 through the dispatch. It falls into 0x84, so it sets BOTH flag bits — swapping the two handlers in the jump table reddens exactly the two dispatch cases |
| `0x58b5e` | `seqcmd_portamento_up` | 6 | ✅ verified | pattern command 0x84 through the dispatch, plus the sounding-note case that drives all four combinations of bits 6 and 7 over three note values: bit 7 alone does nothing at all |
| `0x58b64` | `seqcmd_clear_flags` | 4 | ✅ verified | pattern command 0x81 through the dispatch |
| `0x58b68` | `seqcmd_set_noise_period` | 4 | ✅ verified | pattern command 0x8b through the dispatch, one operand, and the fall-through into 0x8a and so into 0x87 |
| `0x58b6c` | `seqcmd_noise_oneshot` | 4 | ✅ verified | pattern command 0x8a through the dispatch, and the cancel it arms is driven in the per-frame update: dropping it reddens 120 of the battery's cases |
| `0x58b70` | `seqcmd_noise_alternate` | 6 | ✅ verified | pattern command 0x87 through the dispatch, plus the per-frame cases that drive the flag against the frame toggle both ways |
| `0x58b76` | `channel_sequencer_next` | 4 | ✅ verified | `adda.w #24,a0` and fall through — the tick's way of walking channels B and C, and the reason A0 comes back advanced. Entered directly with channel B armed and channel A left where it was |
| `0x58b7a` | `channel_sequencer_step` | 98 | ✅ verified | every one of the thirteen pattern commands reached THROUGH the 13-word jump table, which is read out of the image so that the dispatch itself is part of each case; tone notes and noise notes at both ends of both ranges; the arpeggio-loop bytes 0xb0..0xbf, including the four past the six-entry table that read on into the code behind it; the instrument bytes 0xc0..0xdf, likewise past the fourteen that exist; the note-length bytes; the sounding-note path, which runs portamento and nothing else; and the flag cut-back to bits 4 and 5 |
| `0x58bdc` | `seqcmd_rest` | 8 | ✅ verified | pattern command 0x80 through the dispatch — the "finished" envelope byte for one note length, and one of only three things that end a sequencer step |
| `0x58be4` | `sequencer_start_note` | 48 | ✅ verified | reached from every note case above, and entered DIRECTLY over four note values crossed with a previous note of 0x10 and of 0xff, which is the tie arm. A note at or above 0x54 sets the out-flag bit and writes `note - 0x54` to the default noise period; below it, neither |
| `0x58c14` | `sequencer_end_step` | 14 | ✅ verified | reached from every step-ending case above, and entered directly over note lengths 0, 1 and 0xff. It stores the cursor back as a 16-bit offset from the module base (`suba.l a3,a1`), which is the one place the pattern pointer becomes relative again |
| `0x58c42` | `channel_frame_next` | 4 | ✅ verified | `adda.w #24,a0` and fall through, entered directly on channel B with its own volume shadow byte |
| `0x58c46` | `channel_frame_update` | 426 | ✅ verified | 244 bytes of code around two embedded tables (the 14 instrument offsets and the 84 note periods, which is why the byte count is larger). It answers THE TONE PERIOD IN D1 and writes no byte for it, so the glue returns it and every case holds that against the oracle's own D1 — nothing else could see it. Driven over: envelope bytes either side of the borrow and either side of the finished sentinel, on the first and last instrument; the arpeggio's six loop points crossed with five cursors including 0xff, where the byte increment wraps rather than reading the 256th byte of a ten-byte table; the note-period index at both ends of the note range crossed with three transposes, which pins the BYTE multiply that wraps into the table; the vibrato at both ends of its travel in both directions; the pitch slide over four steps and three delays; and the out-flags rebuild over ten flag combinations |
| `0x58df0` | `sfx_start` | 60 | ✅ verified | all thirteen shipped effects, each also driven to its own end through the tick; the flag SET after the copy, entered with the flag already up (the state the game's own guarded sites at 0x12944 and 0x13e3c avoid) — the CLEAR before the copy is reproduced but NOT delivered by any case, and is filed under "Unpinned on target" with `music_start`'s; and the number's arithmetic, which is bounded by nothing — `ext.w` + `mulu.w` + `adda.w` means 0x80..0xff read a record from BELOW the table, and 13..0x7f from above it. Effect 12 is verified on BOTH images: pristine, and with the nine bytes `A\MODULE.BAK`'s load leaves over the entity arena zeroed as `clear_actor_arrays` leaves them — which is the image the driver really runs on, and the case asserts the two records differ so that it cannot be testing one image twice |
| `0x58e2c` | `music_start` | 88 | ✅ verified | all five shipped tunes, each also played for 240 frames at both machine speeds; the record it reads asserted against the IMAGE rather than against a transcription of the five records; D0's high half shown to be ignored (`ext.w` overwrites the word from the byte, which is what lets the caller hand over a whole word out of `level_tune_id`); and six numbers past the five tunes, where the BYTE shift wraps and `ext.w`'s sign survives it, so 0x80..0xff resolve below the table |
| `0x1217a` | `sfx_play_6` | 24 | ✅ verified | `../names.txt`. The wrapper's `jsr <n>(a0)` operand and its `move.w #$n,d0` immediate are pinned against the staged image, which is the only place either is written down in the binary; the four sfx wrappers are otherwise byte-identical, so the immediate is the whole of what distinguishes them |
| `0x12192` | `music_stop` | 36 | ✅ verified | `../names.txt`. Calls the module's +434 stop entry and then clears `music_active` a SECOND time, which `sound_stop` has already done — reproduced rather than tidied, along with the `move.w $1776e,d0` it loads into a register the module ignores. The second clear is unobservable by construction (below) |
| `0x121b6` | `sfx_play_10` | 24 | ✅ verified | `../names.txt`, as `sfx_play_6` |
| `0x121ce` | `sfx_play_5` | 24 | ✅ verified | `../names.txt`, as `sfx_play_6` — the most-called wrapper in the game, 10 call sites |
| `0x121e6` | `sfx_play_2` | 24 | ✅ verified | `../names.txt`, as `sfx_play_6` |
| `0x12588` | `music_play` | 20 | ✅ verified | `../names.txt`. D0.w straight through to the module's +1256, driven with the two constants the game passes (0 and 4) and with a word carrying high garbage, which is the shape the 0x125b0 caller's `move.w $1776e,d0` really has |
| `0x1259c` | `music_restart_if_stopped` | 32 | ✅ verified | `../names.txt`, and the game's own use of "the tune has finished". Both guards driven both ways — the stage's suspend word at `A_music_suspend_flag` and the module's `music_active` — crossed with two tune ids |

**Mutation sweep: 40 mutations, 36 red, 4 survivors, and one hole found and closed.** Every one from
a green baseline with `build/libflyingshark.so` deleted and relinked and `__pycache__` swept
(`docs/agent-playbook.md` §10 — and the trap bit once here, when a build that failed under another
agent's concurrent edit left no artifact and the sweep read a live mutation as "no output").

**The hole**: the tie sentinel changed from 0xff to 0x80 SURVIVED the whole battery. Command 0x8c is
normally followed by a NOTE, which overwrites the byte before the step ends, so the sentinel never
reaches the image and only its sign is ever tested — any negative value behaves identically.
`test_a_tie_followed_by_a_rest_leaves_the_sentinel_in_the_note` is the one pattern that makes the
written value observable (a rest ends the step with the sentinel still in place), and the mutation
is red against it.

The four survivors, each argued rather than filed:

| survivor | why it is equivalent rather than uncovered |
|---|---|
| the frame toggle flipped BEFORE the vibrato instead of after | the two are XORs of different bits of one byte and nothing between them reads the toggle, so the C really is the same program either way |
| `music_stop`'s SECOND clear of `music_active` dropped | `sound_stop` has already cleared it and nothing runs between the two, so the original's own redundancy has no observable half. It is reproduced because it is the original's, not because anything can tell |
| the arpeggio's `andi.b #$7f` (0x58c92) keeping bit 7 in the offset | **the mask is DEAD CODE in the original**, and provably: the value it masks is only ever byte-added to the note and the transpose and then DOUBLED AS A BYTE (`add.b d0,d0` @ 0x58ca2) before it indexes anything, and `0x80 * 2 = 0x100` is zero in a byte. Every one of the shipped table's terminated entries would give the same period with the mask gone. Reproduced because it is the original's instruction |
| `sfx_start` setting `sfx_active` before the copy instead of after | off target nothing can interleave with a C call, so the ordering has no observable half. ON target it is the guard against the VBL handler's tick landing mid-copy and reading a half-written parameter block — recorded under "Unpinned on target" below rather than left as a coverage hole |

## Borrowed globals

A global lives in the header of the subsystem that owns the data (README.md, "Adding a function").
A row here is a LOAN: a global defined in a header that does not own it, because the routine that
does is unported. Each row names the address, the name as spelt, the owner, where it is defined
today, and why — and a finished migration DELETES its row and the `#define` it names, so the
table's length reads as outstanding debt rather than as history.

**THE PLAYER SUBSYSTEM'S ELEVEN LOANS ARE PAID OFF and are no longer in this table.** `PLAYER_X`,
`PLAYER_Y`, `PLAYER_FRAME` (from `include/entity.h`) and `A_player`, `PLAYER_MODE`,
`PLAYER_MODE_GAMEOVER`, `A_lives`, `A_bombs`, `A_player_hit`, `A_dl_player_shadow` (from
`include/hud.h`) are defined ONCE, in `include/player.h`, as the seven-byte record and the counters
that go with it; `src/hud.c`, `src/entity.c` and `src/weapons.c` include that header and read them.
`A_weapon_level` went the same way, from `include/entity.h` to `include/weapons.h`.

**The five cheat flags were never a loan and their rows were wrong.** `A_invuln_flag` and its four
siblings stay in `include/hud.h` because `check_cheat_name` @ 0x10e16 and its five handlers — all
`src/hud.c` — are the only things that WRITE them. A global lives with the subsystem that owns the
DATA, and the data is the cheat state; the player and weapons cores are readers, and a reader
includes the header. `A_player_hit` is the one the cheat writes that really is the player's, and it
moved with the record.

**THE SCROLL SUBSYSTEM'S FIVE LOANS ARE PAID OFF and are no longer in this table.**
`A_map_row_ptr`, `A_map_row_ptr_reset`, `A_scroll_fine` and `A_prescroll_flag` (from
`include/sprite.h`) and `A_scroll_pos` (from `include/hud.h`) are defined ONCE, in
`include/scroll.h`, which owns the scroller block at 0x163da..0x16436 and the two scroll counters in
bss. `A_screen_ring_index` and `A_tile_split_row_table` moved with them although they never had rows
— they sat in the same borrowed block — and `A_level_number` @ 0x1642a deliberately did NOT: it is
inside the same address run but it is the level-flow state `include/player.h` owns, and one address
has one home whatever its neighbours are. `include/sprite.h` and `include/hud.h` now include
`include/scroll.h`; the batteries that mirrored those defines were repointed at the new path in the
same change.

**THE IRQ SUBSYSTEM'S FOUR LOANS ARE PAID OFF and are no longer in this table.** `A_joy0_state`,
`A_joy1_state`, `A_key_bits` and `A_key_last_scancode` are the ACIA handler's — `src/irq.c` is
their only writer, and `tos_joyvec_handler` (dead on the machine) the only other — so they are
defined ONCE, in `include/irq.h`, beside `A_vbl_tick`, which is the same argument at the VBL's
counter. They were declared by the subsystems that READ them, which was the opposite of every other
row here; `include/player.h` and `include/hud.h` now include `include/irq.h` and the four batteries
that mirrored them were repointed at the new path in the same change.

**THE TUNE ID'S LOAN IS PAID OFF TOO.** `0x1776e` `level_tune_id` said "frontend" and its only
writer is `start_level` @ 0x11484 — the SCROLL subsystem's — so it is defined in
`include/scroll.h` now, beside the `LEVEL_REC_TUNE` field it is copied out of, and `src/sound.c`
includes that header to read it.

**ONE ROW BELOW IS NOT A CENSUS QUESTION AND STAYS.** `0x176a4` `music_suspend_flag` said "frontend"
and now says what the image says: THREE subsystems write it — `player_vs_enemy_bullets` @ 0x110be
and `restart_level_at_checkpoint` @ 0x14be0 (player), `init_stage_state` @ 0x113ca (init) — and only
the sound driver reads it. The rule that settled every other row ("a global lives with the subsystem
that owns the data") does not pick a winner here, so it stays in `include/sound.h`, with the reader
as its home, until somebody argues one.

**No header includes another to reach one of these**, which is what keeps the migration mechanical:
`include/player.h` includes `hud.h` and `entity.h` for its own core's sake, and the borrowing goes
the other way round through the `.c` files. A move that needed a header cycle would be a sign the
global belonged somewhere else.

| Addr | Name | Owner | Defined in | Why on loan |
|---|---|---|---|---|
| `0x176a4` | `music_suspend_flag` | THREE writers; no owner the census picks | `include/sound.h` | `music_restart_if_stopped` @ 0x1259c reads it as its first guard, and is the only reader. Written by `player_vs_enemy_bullets` @ 0x110be and `restart_level_at_checkpoint` @ 0x14be0 (player) and by `init_stage_state` @ 0x113ca (init) — all three ported, so this is not a loan waiting on a subsystem. It stays with its reader because "the subsystem that owns the data" names nobody here; closing it means somebody arguing one of the three, and editing `include/sound.h` and `test_sound.py`'s mirror row |
| `0x177cc` | `A_hard_mode` | frontend | `include/hud.h` | `game_over_hiscore_check` @ 0x10724 clears it; the title screen's left/right toggle sets it |
| `0x16132`, `0x16136` | `A_title_word_easy`, `A_title_word_spam` | frontend | `include/hud.h` | `check_cheat_name` @ 0x10e16 copies one over the other, which is how the title's "MODE EASY" becomes "MODE SPAM" |

**The predicted loan did NOT happen.** `include/globals.h` keeps `A_entity_arena`, `ENTITY_SLOTS`
and `ENTITY_STRIDE` because the arena's PLACEMENT is part of the memory model. `include/entity.h`
includes that header and re-defines none of the three; the frozen 58-byte record layout lives beside
them, every field tagged `pinned by <test>` or `names.txt, unpinned`, as
`projects/zynaps/recreate/include/entity.h` does it (`docs/agent-playbook.md` §11).

## Follow-ups the kit should absorb

Not this project's to fix, and recorded here so the next agent to touch the kit finds them rather
than making a fourth copy.

| What | Where it is copied | Why it belongs in the kit |
|---|---|---|
| `test/test_heap_guard.py` | near-verbatim in `projects/joust`, `projects/zynaps` and here | the file is entirely about the KIT's `tos_malloc_unused` waiver; only the game's name, its bss bounds and the `project.toml` prose differ. The Malloc stub itself is already hoisted (`recreate_kit.stubs.gemdos_malloc_stub`) and this file now calls it |
| `test/abi.py`'s `register_call_pokes` / `_store_through_a0` | verbatim from `projects/zynaps` | a `move.l <reg>,(a0)+` stub is 68000 encoding, not this game's ABI. What IS this project's is the scratch map around it and the reason the ring cannot hold it |
| `test/test_constants.py`'s and `test/test_status.py`'s collectors | ported from `projects/bubbleghost` (originally Joust's) | the discovery rules (`MIRRORS`, `ENTRY_PROLOGUES`, the STATUS.md section grammar) are conventions the kit defines; every project restating them is how one project's fix stops being everyone's |
| an EMPTY schedule counts 0 arrivals at every wait site | `oracle/shim.c`'s arrival counting, keyed on `g_sched_n` | a wait whose input is already present makes no arrival, which is a legitimate case — but with no schedule entry at all the counter never arms, so the candidate's polls are compared against 0 rather than against "none due". `test_hud.py`'s two wait sites carry a DUMMY entry (an arrival that can never come due) to get the count armed, which is a workaround in a battery for a shim behaviour |
| there is no `sched_poll32` | `tools/recreate_kit/include/sched.h`, which has `sched_poll8` and `sched_poll16` | `render_frame`'s VBL wait compares a LONGWORD (`move.l $17720,d1` @ 0x1479c). `src/sprite.c` spells it as `sched_poll16`'s shape one width up — one poll an iteration for the clock, then a full-width read — which loses that wrapper's own CAP and nothing else. A third width would make the wait one call again |
| `test/abi.py`'s five stub builders | `register_call_pokes`, `register_dump_pokes`, `extend_call_pokes`, `call_sequence_with_d0_pokes` and the `_stub`/`_jsr` frame under them, all from `projects/zynaps` | none of them is this game's: they are 68000 encodings for driving a register-ABI routine under an oracle, which every project with one needs. What IS this project's is the scratch map they are poked into and the argument for where it sits |
| `SCC_TRUE` and `addr_sub` | `include/common.h` here; the same two facts in Joust's, Zynaps' and Bubble Ghost's cores under other names | neither is about Flying Shark. `SCC_TRUE` is what a 68000 `Scc` writes and `addr_sub` is a backward pointer step, and `machine.h` already owns `addr_add`, `loop_passes` and `rotate_right32` for exactly that reason. `include/common.h`'s header says so |
| the staged-file window holds 258,048 bytes, and this program's own boot loads 288,551 | `test/conftest.py`'s three-slice replay, and README.md's "The image model", both of which exist to work around it | `OS_FS_STAGING` runs from 0xc0000 to the stack guard, so a game whose boot chain loads eight files in one go cannot be replayed in one run — the fixture splits `init_load_assets` in two and `main`'s BOOT slice ("Not reconstructed") has no row at all. It is 30,503 bytes short, and everything that would close it is the kit's: a second staging window, or a bigger `OS_IMAGE_SIZE` with the area moved up. `OS_FS_SLOTS` went 8 -> 32 for Zynaps for the same class of reason, so the precedent is a kit constant moving rather than a project working round it |
| XBIOS `Physbase`/`Logbase` has no `os_*` door | `src/init.c` asks through `include/init.h`'s `fs_physbase()`, which returns `OS_SCREEN_BASE` | every other trap the kit models has a named inline in `os.h` — `os_super`, `os_fopen`, `os_setpalette`, `os_ikbd_out` — so a core reads as what it does. This one is the exception, and a reconstruction that spells the constant is compiling in an answer rather than asking for one: on an ON-TARGET build (the include-path seam) `os_physbase()` would issue the real XBIOS call. It is a two-line inline and needs no shim change; `fs_physbase()` is the one place to swap |
| XBIOS `Kbdvbase` has no `os_*` door, AND ITS ANSWER IS NOT AN IMAGE OFFSET | `src/init.c`'s `boot_init` asks through `include/init.h`'s `fs_kbdvbase()`, which returns `OS_KBDVBASE`, and then writes TOS's joyvec slot with `wr32(image + joyvec_slot, ...)` | this is a bigger gap than the Physbase row above it and is split from it for that reason. `OS_KBDVBASE` is a small number INSIDE the modeled image, so `image + it` is a legal index; a real `Kbdvbase()` returns a TOS pointer into ROM-owned RAM, which is not an offset into this program's image at all and which `image +` would send somewhere arbitrary. Closing it needs BOTH an `os_kbdvbase()` door and a core that reaches the struct through an absolute-address accessor rather than through `image +` — which is a kit shape (a `mem_wr32(addr)` that is the identity off target) rather than a `#define` |
| the `Setscreen` ledger event carries ONE base | `tools/recreate_kit/include/os.h`, `os_setscreen` @ os.h:389 | the call takes a logical AND a physical base and the event records only the logical one, so a game that publishes frames by changing the PHYSICAL base — this one does, every frame — has the whole content of the call dropped. A two-argument event would make `render_frame`'s publish comparable off target, and it is the first row of "Unpinned on target" below |

## Unpinned on target

Things the differential is structurally blind to, recorded here rather than discovered on an Atari.
`docs/on-target-execution.md`, "The observable surfaces", is the taxonomy.

| What | Why the harness cannot see it | What would |
|---|---|---|
| `vbl_handler`'s chain tail — the `jmp` at 0x1164e whose operand `boot_init` fills from `$70` | the TOS model has no vector at `$70`, so the fixture holds 0 where an Atari holds TOS's own level-4 handler. Both sides read the same 0, so the diff agrees with itself (`test/conftest.py`, "what it does not hold") | an on-target run: the surface is TOS's blank-time housekeeping (`_frclock`, `_v_bas_ad`) still advancing under a program that owns the vector |
| where the screen ring actually is | the model's `Physbase` (`OS_SCREEN_BASE` = 0x8000) underflows `boot_init`'s `- 0x1f900`, so the harness PLACES the ring at 0x60000 instead of taking the model's answer (`README.md`, "The image model"). The arithmetic is pinned; the address is the harness's choice | an on-target run: the surface is rendered pixels — a ring in the wrong place shows as a scroll that tears or wraps at the wrong row |
| what the IKBD `Bconout(4, $14)` and the `Kbdvbase` joyvec install DO | **the two calls themselves are pinned now** — `boot_init`'s row above verifies both: the command is an ordered OS EVENT the harness compares, and the joyvec save/install are ordinary image stores at `OS_KBDVBASE + 0x18` (0x518, well below the poked-input block at 0x600, which `test_init.py` asserts). What no differential can reach is their EFFECT: that the 6301 then really sends $FE/$FF-prefixed packets, and that TOS's parser would really call the vector — both live in a chip and an OS the model does not have | an on-target run: the surface is joystick input arriving at all. Its absence is the `Bconout` never having been issued |
| everything `Setpalette` / `Setscreen` / `Vsync` do | modeled as ordered OS events with no image effect (`tools/recreate_kit/TRAP_MODEL.md`, Phase 14) | the event ledger for the calls, and rendered pixels for their effect |
| the PHYSICAL screen base `render_frame` publishes | `Setscreen`'s ledger event carries only the LOGICAL base, and this game always passes -1 for it — so the physical base, which is the whole point of the call, is dropped by `os_setscreen` (`tools/recreate_kit/include/os.h`, "the XBIOS VIDEO AND COLOUR GROUP"). Every frame case therefore compares a call that says nothing about WHICH screen was published | an on-target run: the surface is rendered pixels, and a wrong base shows as a frame drawn into a buffer nobody is looking at. Off target it needs the two-argument ledger event named under "Follow-ups the kit should absorb" |
| `music_start`'s and `sfx_start`'s CLEAR-BEFORE-FILL of the module's parameter block | BOTH are unobservable off target and for one reason: nothing can be interleaved with a C call, so a block that is cleared and then filled ends at the bytes the fill wrote, whatever the clear did. `sfx_start`'s flag ordering (row below) is the same argument at one byte; this is it at the whole block. Neither routine's clear has a surface here, and the STATUS row for 0x58df0 no longer claims one | an on-target run with the VBL live: the clear is what stops `vbl_handler`'s tick reading a half-written block on the frame an effect or a tune starts, so the symptom is one frame of the wrong period or duration |
| `sfx_start`'s clear-then-fill-then-set of `sfx_active` | off target a C call cannot be interleaved with anything, so setting the flag first and last leaves the same final block; the mutation that does so SURVIVES the whole battery. On the machine the flag is the guard against `vbl_handler`'s tick landing mid-copy and running a half-written parameter block | an on-target run with the VBL live: the surface is what the chip is fed on the frame an effect starts, so a burst of the wrong period or duration for one frame is the symptom |
| which machine speed the driver is really on | `$ff820a` bit 1 is a DECLARED case input (`hw_seed=`), so every case states the machine rather than measuring it. Both settings are driven, and the divider is pinned at every phase — but that the ST answers bit 1 set at all is the model's claim, not this reconstruction's | an on-target run: the surface is the music's tempo, which is 20% out if the branch goes the other way |
| `probe_disc`'s NEGATIVE arm — the `bmi` that skips the `Fclose` when disc A is out | an `Fopen` of a name the harness has not staged is a REFUSAL on both sides: it sinks the ORACLE's whole run (`g_unmodeled`) and tallies against the candidate (`_vet_no_os_refusal`), so a case for "the disc is out" is a case the model throws away rather than one it answers -1 to. The mutation that closes a negative handle anyway therefore SURVIVES the battery, and cannot not (measured 2026-09-07) | an on-target run with the drive empty: the surface is the trap ledger — a `Fclose` of a negative handle, and the "INSERT DISC A" prompt that is supposed to spin on the probe |
| WHERE in an ACIA handler the `bclr #6,$fffffa11` falls | the end-of-interrupt is an off-image HARDWARE WRITE and everything around it is an image write, and the harness compares the two as SEPARATE ordered streams — so moving the `bclr` from after the key ladder to before it leaves both streams unchanged and the mutation SURVIVES (measured 2026-09-07). It is the same shape as the sound module's clear-before-fill two rows down: an ordering nothing off target can interleave | an on-target run with the IKBD live: the surface is whether a second ACIA byte arriving mid-handler is serviced or lost, which is a keypress the game misses |
| the sequencer's pattern cursor has no upper bound | `sequencer_fetch` walks forward until a byte ends the step, and the original has no check at all; the oracle bounds its reads at the image's end while the C indexes `image` directly. Every reachable pattern in `A\MODULE.BAK` ends a step within a few bytes, so nothing in the battery — including `make guarded`'s 744 candidate runs — reaches the walk | nothing off target: it needs a pattern the game's own data cannot produce. Recorded so that a future edit to the module's data is known to be able to run the cursor off the image |

## Not reconstructed, and why

**This must stay the LAST section of the file**: `test_status.py` reads the deferral table from this
heading to the end, so a section added below it would have its hex read as deferred addresses.

Every `fn` line in `../names.txt` with no ✅ row above eventually appears here, with the reason:
unreachable under the model, a model gap, or simply not yet started.

**WHAT IS LEFT HERE IS NOT "not started".** The table opened as a wave-1 scaffold — filing the first
✅ row arms `test_status.py::test_every_named_function_is_verified_or_deferred`, which from that
moment demands that every `fn` line in `../names.txt` be accounted for — and waves 2 and 3 emptied it
down to the six rows below. Each is a MODEL BLOCKER, a routine whose own shape has no checkpoint, or
dead code, and each row says which. The grouping by subsystem is from the name map's own names; the
addresses are exact. **An agent who verifies one of these deletes its address from its row in the same change
that files the ✅ row** — which is what the gate says, by address, when it goes red.

THE ENTITY SLICE'S TWO SEAMS ARE CLOSED, not merely verified: `0x10b8c` (`score_add_1000`, on the
bonus-item drop's arm, by the hud slice) and `0x121e6` (`sfx_play_2`, by the sound slice) are both
CALLED by `src/entity.c` now, so neither is in this table and no routine in it stops at a `bsr`.

| Routine(s) | Subsystem | Why not, and what would close it |
|---|---|---|
| `0x10e6a` | hud | `movea.l #$0,a0 / jsr (a0)` — it deliberately calls address zero. A booby trap, not a feature (../notes/frontend.md §6), and running it under the oracle executes whatever the vector page holds. `check_cheat_name`'s dispatch carries an explicit arm for it that does nothing, and its fuzz drops any name that would reach row 4. NOTHING would close this: the routine has no behaviour to verify, only a crash to record |
| `0x15750` | init | `main`'s three-call BOOT slice [0x15750, 0x1575c), and it is TWO MODEL BLOCKERS rather than effort. (1) `bsr init_load_assets` loads EIGHT files whose bytes total 288,551, and the kit stages files in ONE window — `OS_FS_STAGING` up to the stack guard, 258,048 bytes — which is 30,503 short (README.md, "The image model", is where the fixture's own split comes from). It is a KIT SIZE and not a fact about this game: the row under "Follow-ups the kit should absorb" carries it, with the `OS_FS_SLOTS` 8 -> 32 change Zynaps needed as the precedent. (2) `bsr init_new_game` NEVER RETURNS: it ends `bra.w enter_title`, so the run never reaches the third call, and the attract loop that eventually `rts`es back is a joystick spin. Its LOOP is verified above as `frame_loop_once` @ 0x1575c, which is the 45-call body and the `clr.w` that ends it; what has no row is the composition of the three inits |
| `0x1030e` `0x104f2` `0x10594` | frontend | The three routines of the title FLOW, and all three are blocked on their own SHAPE rather than on anything missing — `set_palette_black` and `set_palette_game`, which the stated blocker used to name, are verified under `init` now. `enter_title` is four instructions between a `bsr` and a `bra title_attract_loop`; `title_attract_loop`'s own body past 0x1054a and `title_frame_step` are ONE spin loop with four exits — a `bsr set_palette_game`, a poll of the sound module's byte at +30, a joystick test and a branch back into each other — so neither has a single checkpoint a slice could be diffed at. Their SETUP is verified: 0x104f6 above is 84 of `title_attract_loop`'s bytes. What would close them is a `frame_loop_once`-shaped core over the whole spin with a SCHEDULE for the module poll and the joystick, which is a case shape this project has (`test_hud.py`'s wait sites) and has not applied here |
| `0x1581a` | sprite | `tile_blit_unreferenced`: DEAD AND BROKEN, and it will stay in this table. NO instruction in the image names its entry — it sits after `main` at the end of TEXT — and its two clipped entries cannot work: the clip arithmetic scales the row count by 10 bytes a row (`mulu.w #$a`) while the unrolled block it jumps into steps 12 (four `move.l` + `lea 144(a0),a0`), so either clipped entry lands mid-instruction. Reaching it needs a caller that does not exist, and running it would need the bug fixed — which would make the reconstruction a remaster. The live tile drawing is the inline loop inside `render_frame` (0x1483a) and `tile_blit_overlay_masked`, both verified |
| `0x14aa8` | player | The two instructions before that slice's start: `bsr set_palette_black` @ 0x111a6 and `st level_just_started`. `0x14aac` — the whole of the rest of the routine up to `clear_actor_arrays` — IS verified above, and this row is the ENTRY. **ITS STATED BLOCKER IS GONE:** `set_palette_black` and `clear_actor_arrays` are both verified under `init` now, so the whole-routine differential the row was waiting for is available and this is a row to close rather than a routine to think about |
