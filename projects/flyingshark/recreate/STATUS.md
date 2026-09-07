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

**Nothing is ported yet.** This is the harness skeleton: the binding, the image model and the gates
that will catch a wave of subsystem agents getting them wrong. The ten sections below are empty
placeholders so that the first agent into each finds a heading rather than inventing one; a section
stays exempt from `src/<name>.c` existing only while it carries no rows.

**The image model is README's, not this file's.** Where the screen ring is placed, what the
post-load fixture holds and what it deliberately does not are decided in [`README.md`](README.md),
"The image model", and pinned by `test/test_image_model.py`. Nothing here restates it.

**How to add a function:** [`README.md`](README.md), "Adding a function" — the procedure, the file
ownership table and the conventions all live there rather than being restated here.

## Suite

**51 tests: 47 passed, 4 skipped** — `test_image_model.py` 30, `test_constants.py` 8,
`test_heap_guard.py` 8, `test_status.py` 5. Measured 2026-09-07 with
`rm -f build/*.so && find . -name __pycache__ -exec rm -rf {} + && make test`. `make guarded` runs
the same 51 (Darwin/BSD only) and reports 1 guarded candidate run — the heap guard's, which is the
only case in this skeleton that runs a candidate at all.

The FOUR skips are the gates that are not armed yet, and each says so loudly rather than passing
over an empty list: `test_status.py::test_every_named_function_is_verified_or_deferred` while the
ledger carries no row, and `test_constants.py`'s three battery gates while `src/` holds no `.c`.

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

## Verified — init (0)

## Verified — frontend (0)

## Verified — scroll (0)

## Verified — sprite (0)

## Verified — entity (0)

## Verified — player (0)

## Verified — weapons (0)

## Verified — hud (0)

## Verified — irq (0)

## Verified — sound (0)

## Borrowed globals

A global lives in the header of the subsystem that owns the data (README.md, "Adding a function").
A row here is a LOAN: a global defined in a header that does not own it, because the routine that
does is unported. Each row names the address, the name as spelt, the owner, where it is defined
today, and why — and a finished migration DELETES its row and the `#define` it names, so the
table's length reads as outstanding debt rather than as history.

| Addr | Name | Owner | Defined in | Why on loan |
|---|---|---|---|---|

*(empty: nothing is ported, so nothing is borrowed. `include/globals.h`'s contents are not loans —
they are the memory model itself, and it is nobody's to edit.)*

**One loan is predicted.** `include/globals.h` carries `A_entity_arena`, `ENTITY_SLOTS` and
`ENTITY_STRIDE` because the arena's placement is part of the memory model, but the 58-byte RECORD
LAYOUT is the entity subsystem's and belongs in `include/entity.h` when that lands — frozen in one
block, every field tagged `pinned by <test>` or `names.txt, unpinned`, as
`projects/zynaps/recreate/include/entity.h` does it (`docs/agent-playbook.md` §11). The agent who
writes that header must NOT re-`#define` the three names above:
`test_constants.py::test_no_constant_is_defined_in_two_files` is what will say so, in their diff.

## Follow-ups the kit should absorb

Not this project's to fix, and recorded here so the next agent to touch the kit finds them rather
than making a fourth copy.

| What | Where it is copied | Why it belongs in the kit |
|---|---|---|
| `test/test_heap_guard.py` | near-verbatim in `projects/joust`, `projects/zynaps` and here | the file is entirely about the KIT's `tos_malloc_unused` waiver; only the game's name, its bss bounds and the `project.toml` prose differ. The Malloc stub itself is already hoisted (`recreate_kit.stubs.gemdos_malloc_stub`) and this file now calls it |
| `test/abi.py`'s `register_call_pokes` / `_store_through_a0` | verbatim from `projects/zynaps` | a `move.l <reg>,(a0)+` stub is 68000 encoding, not this game's ABI. What IS this project's is the scratch map around it and the reason the ring cannot hold it |
| `test/test_constants.py`'s and `test/test_status.py`'s collectors | ported from `projects/bubbleghost` (originally Joust's) | the discovery rules (`MIRRORS`, `ENTRY_PROLOGUES`, the STATUS.md section grammar) are conventions the kit defines; every project restating them is how one project's fix stops being everyone's |

## Unpinned on target

Things the differential is structurally blind to, recorded here rather than discovered on an Atari.
`docs/on-target-execution.md`, "The observable surfaces", is the taxonomy.

| What | Why the harness cannot see it | What would |
|---|---|---|
| `vbl_handler`'s chain tail — the `jmp` at 0x1164e whose operand `boot_init` fills from `$70` | the TOS model has no vector at `$70`, so the fixture holds 0 where an Atari holds TOS's own level-4 handler. Both sides read the same 0, so the diff agrees with itself (`test/conftest.py`, "what it does not hold") | an on-target run: the surface is TOS's blank-time housekeeping (`_frclock`, `_v_bas_ad`) still advancing under a program that owns the vector |
| where the screen ring actually is | the model's `Physbase` (`OS_SCREEN_BASE` = 0x8000) underflows `boot_init`'s `- 0x1f900`, so the harness PLACES the ring at 0x60000 instead of taking the model's answer (`README.md`, "The image model"). The arithmetic is pinned; the address is the harness's choice | an on-target run: the surface is rendered pixels — a ring in the wrong place shows as a scroll that tears or wraps at the wrong row |
| the IKBD `Bconout(4, $14)` and the `Kbdvbase` joyvec install | neither writes an image byte the fixture carries: the first is an OS-event-ledger entry, the second would store into the model's own poked-input block | an on-target run: the surface is the trap ledger, plus joystick input arriving at all |
| everything `Setpalette` / `Setscreen` / `Vsync` do | modeled as ordered OS events with no image effect (`tools/recreate_kit/TRAP_MODEL.md`, Phase 14) | the event ledger for the calls, and rendered pixels for their effect |

## Not reconstructed, and why

**This must stay the LAST section of the file**: `test_status.py` reads the deferral table from this
heading to the end, so a section added below it would have its hex read as deferred addresses.

Every `fn` line in `../names.txt` with no ✅ row above eventually appears here, with the reason:
unreachable under the model, a model gap, or simply not yet started.

| Routine(s) | Subsystem | Why not, and what would close it |
|---|---|---|

*(empty. `test_status.py::test_every_named_function_is_verified_or_deferred` SKIPS while both this
table and every `## Verified` section are empty, and ARMS at the first row filed in either — from
then on every `fn` line in `../names.txt` must have a ✅ row or a row here, and never both. How many
that is, is the name map's business and is deliberately not written down: the skip message reports
the number it counted, and a literal here would be one more figure nobody recomputes. So the first
agent to file a verified row also starts this table for what their slice left behind.)*
