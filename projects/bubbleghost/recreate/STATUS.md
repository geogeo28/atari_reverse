# Reconstruction status — Bubble Ghost

Human-readable C reconstruction of Bubble Ghost (ERE Informatique, 1987), each function **verified
byte-for-byte against the original 68000 code** by the shared differential harness
(`tools/recreate_kit`: a Musashi oracle running the real code vs. the compiled reconstruction, on
the same memory image). `../names.txt` is the source of truth for every name.

**Verified: the sum of the per-section counts below**, out of the **134** functions Ghidra found in
this program (`../notes/anchors.md`, "Shape of the image" — that is the whole code segment: the
31 KB running to the end of TEXT is `init_globals`' own instruction stream, not undiscovered code).
Three of the six sections carry rows today — `blit`, `sound` and `clib`, the subsystems with no game
logic in them. `init`, `frontend` and `gameplay` are still headings waiting for their first
function.
Each `## Verified — <subsystem>` heading carries its own count, so the only number an agent touches
is its own section's; `test/test_status.py` fails if a count and its rows disagree, if a section that
carries rows names a subsystem with no `src/<name>.c`, and if a literal grand total creeps back into
this header.

**The image model is README's, not this file's.** Why the harness loads `../bin/GHOST_RT.PRG`, what
the post-init fixture is, and why every case passes `a4 = 0x24f1a` are decided in
[`README.md`](README.md), "The image model", and pinned by `test/test_image_model.py`. Nothing here
restates it.

**How to add a function:** [`README.md`](README.md), "Adding a function" — the procedure, the file
ownership table, and the conventions all live there rather than being restated here.

## The suite, and what it is proved to catch

**The skeleton's own gates are 31 tests** — `test_image_model.py` 22, `test_constants.py` 6,
`test_status.py` 3 — with each battery's cases on top of them, so the suite total is not a number
to carry here: re-count it with `rm -f build/*.so && make test` and report your own battery's share.
The kit's suite behind it measured **631** (`make -C tools/recreate_kit test`) when this was
written — a number that moves with the kit rather than with this project, so re-run it rather than
quoting it.

**Mutations tried against the skeleton's gates**, each rebuilt from a clean `build/` with
`__pycache__` swept, and each **red**:

| mutation | what stayed honest |
|---|---|
| `test_image_model.py`'s `A4_BASE` off by 2 | the `include/globals.h` mirror, and both .PRG headers' derivation of it |
| `conftest.py`'s `INIT_GLOBALS_A5` set to 0 | the crt0 equivalence — the seven `lea n(a5),a0` pointers land in low memory instead |
| `test/abi.py`'s `STUB` moved to 0x80000 | the arena/scratch-map boundary: it must equal `project.toml`'s `heap_limit` |
| `project.toml`'s `heap_limit` raised to 0xa0000 | the same boundary, from the other side |
| `project.toml`'s `heap_base` moved into the program | the kit refuses at IMPORT — the whole suite errors, by name |
| a `## Verified — <x> (N)` count raised by one | `test_status.py`'s per-section re-derivation |
| `src/<x>.c` with its `test_<x>.py` renamed away | `test_constants.py` now names the missing battery instead of dropping the stem — observed live rather than injected, on a tree that carried `src/sound.c` before its battery landed |
| the autouse base-image fixture removed | `test_every_differential_starts_from_the_post_init_image` |
| `conftest.py`'s stated `INIT_GLOBALS_INSNS` off by one | the fixture's measured cost, re-run |
| the Malloc census's palette counted per picture | `test_the_derived_malloc_census_is_the_one_the_prose_quotes` — the exact error the old `0x3d5e4` constant carried |

Every row above was **run**, from a clean `build/` with `__pycache__` swept, against the green
subset `test_image_model.py + test_status.py`. A mutation the suite does not catch is a coverage
hole, not a licence — record it here.

## Model gaps — read this before picking a function

The kit's TOS trap model (`tools/recreate_kit/TRAP_MODEL.md`) was built for the games before this
one, and Bubble Ghost reaches OS calls none of them did. **An unmodeled call is not a wrong answer,
it is a refused run** — `emu.run` raises and names it — so nothing here can silently produce a false
green. What it does mean is that the routines below cannot be ported until the gap is closed, and
the gap is a KIT change in every case. Counted from the 92 trampoline call sites (`gemdos_trap` @
0x15e58, `xbios_trap` @ 0x15e3c), by the selector immediate pushed at each.

**One gap has been closed since the bootstrap** and is recorded here rather than dropped, because
the reasoning is still the map's: the kit's Malloc arena used to be a kit-wide `#define` at 0x20000,
inside this program's BSS, and the only knob was `tos_malloc_unused` — a claim ("this game never
allocates") that is false here. The kit now places the arena per project (`heap_base` /
`heap_limit`; the mechanism is in
[`tools/recreate_kit/README.md`](../../../tools/recreate_kit/README.md), "The Malloc arena is the
one region a project places", and this game's numbers are in [`README.md`](README.md)), this
project uses `[0x30000, 0x90000)`, and the waiver is gone.

| gap | where it bites | what closing it needs |
|---|---|---|
| **GEMDOS `Cconis` (0x0b), 6 sites** | every keyboard poll — the menu's "Press [G]…[P]…[D]…[H]", the pause, the name entry | a model over the poked console state, beside the existing `Bconstat`. The state is already there (`OS_CON_PENDING`); the selector is not |
| **GEMDOS `Crawcin` (0x07), 7 sites / `Cnecin` (0x08), 4 sites** | the same keyboard paths, on the blocking side | the same block, plus a decision about what a BLOCKING read does when nothing is pending. `Crawio` (0x06, modeled, 2 sites) is the non-blocking one and is the precedent |
| **GEMDOS `Fseek` (0x42), 5 sites** | the hall-of-fame file (`GHOST.SCR` read @ 0x121a0, written @ 0x1207a) | the staged-file table already holds a cursor (`OS_FS_OFF_CURSOR`); `Fseek` is the one accessor of it the model never grew |
| **GEMDOS `Fdelete` (0x41) / `Pterm` (0x4c) / `Cauxin` (0x03) / `Cauxout` (0x04) / `Cprnout` (0x05), 1 site each** | the C library's own wrappers (0x16868, 0x14d16, 0x16666, 0x16bae, 0x16bdc) — `clib` work, almost certainly unreachable in play | nothing, until someone ports those wrappers. Record them read-verified rather than growing the model for a path the game never takes |
| **BIOS `Bconout` (trap #13), 2 sites** | `game_top_loop` @ 0x101e6 only: the two IKBD commands `$12` (disable the mouse) and `$08` (relative reporting back on) | the shim models BIOS 0x01/0x02 and nothing else. XBIOS `Ikbdws` (0x19) is already modeled as a no-op, which is the shape `Bconout` to device 4 wants |
| **`trap #2` (GEM), 2 trampolines** | the AES one @ 0x149b6 (`d0 = $c8`) and the VDI one @ 0x168d4 (`d0 = $73`), both on the boot path out of `game_top_loop` | `os_gem_trap` models exactly three opcodes — AES `appl_init` and `graf_handle`, VDI `v_opnvwk` — and REFUSES the rest. This game passes neither: 0x14c1e writes AES contrl[0] = `$4e` (`graf_mouse(M_OFF)`, hiding the GEM pointer) and 0x16a06 writes VDI contrl[0] = 3 (`v_clrwk`), per `../notes/anchors.md`. Both want a modeled opcode each; `v_clrwk` also clears the screen, which is image state and so is not a no-op |
| **`trap #9`, 1 site** | every PSG access from ordinary code: `psg_access` @ 0x14940 calls the game's OWN supervisor gate `trap9_psg_handler` @ 0x14950 | not a TOS trap at all, so the shim does not intercept it: the oracle dispatches through the vector at `$a4`, which is **zero unless the run has already executed `install_sound_vectors` @ 0x148ea**. A reconstruction cannot trap; it calls `psg_port_write()`/`psg_port_read()` from the kit's `psg.h` (TRAP_MODEL.md, Phase 6), and the ledger comparison is what holds the two equal |
| **the Timer C ISR @ 0x1459a** | the music/sound player, installed at `$114` by `install_sound_vectors` | the model fires no interrupts, so the handler is entered explicitly by a stub that builds a 68000 exception frame — copy `interrupt_frame_pokes` from `projects/zynaps/recreate/test/abi.py`. It exits by pushing TOS's saved `$114` and `rts`ing, not by `rte`, so the stub's frame is not popped the usual way: read the tail before writing the case |
| **the model's `Logbase` is 0x8000, and this game's back buffer is `Logbase - 0x7d00`** | `init_video_and_heap` @ 0x10118, and any draw routine driven from the pointers it stores | that puts the back buffer at **0x300**, so a 0x7d00-byte frame write covers `OS_KBDVBASE` (0x500) and the whole harness-poked input block (0x600..0x61f). Both sides do it identically, so the diff stays clean — but a case that ALSO stages a console key silently loses it. Stage the two screen pointers as test inputs rather than taking them from `init_video_and_heap`'s output |
| **`GHOST.LOA` is a second program, `jsr`ed inside the BSS** | `play_voice` @ 0x13cea (`jsr a4-5982`) | it is an `ABSFLAG` `.PRG` read into `a4-6010` as data, with its sample pointer poked at +0x1e (`../notes/loader.md`). Running it means staging the file's bytes into the image first; it programs MFP Timer A and busy-waits, so it also needs Phase 8's scheduled writes or a slice that stops short of the wait |

**What is modeled and needs no work**, so that this list is not read as "the OS is unusable": every
XBIOS call the game makes — `Setscreen` (17 sites), `Setcolor` (5), `Random` (4), `Setpalette` (3),
`Vsync` (3), `Logbase` (2), `Getrez` (2) and `Supexec` (2, which really runs the routine nested) —
plus GEMDOS `Cconout`, `Crawio`, `Super`, `Fcreate`, `Fopen`, `Fclose`, `Fread`, `Fwrite`, `Malloc`
and `Mfree`. The video and colour calls are modeled as **no-ops**, which is the standard limit: they
write hardware, not the image, so the differential cannot see a wrong palette or a wrong screen base
at all (`docs/on-target-execution.md`).

## Verified — init (0)

The boot chain: `crt0_start` @ 0x10036, `init_globals` @ 0x16d8e, `main` @ 0x100dc, `init_video_and_heap` @
0x10118 and `game_top_loop` @ 0x101e6. Every one of them is a slice rather than a function — the loop
never returns — so each row's Verification column opens with the `[start, end)` the differential
actually runs.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|

## Verified — frontend (0)

The presentation screen, the menu, the attract/demo playback and the hall of fame.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|

## Verified — gameplay (0)

The bubble, the fans, the collision and the room logic — the drawing code is expected to dominate.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|

## Verified — blit (11)

The RAW blitters: the `move.l (a3)+,(a2)+` copies over the two screens, and the 32x32 tile draw
every background paint shares. `src/blit.c` has the map of which routine is which; the geometry and
the two screen pointers live in `include/blit.h`, which owns them.

Every case stages the world itself rather than taking it from a routine's output, and
`test/test_blit.py`'s module docstring says why: the model answers `Logbase` with 0x8000, so
`init_gem_and_screens`' `Logbase - 0x7d00` work buffer would land at 0x300, on the harness-poked
input block (the "Model gaps" row). So `screen_phys`/`screen_back` are poked at addresses inside
`test/abi.py`'s scratch map that keep the machine's own relationship, the six GHOST.DAT banks are
staged in the Malloc arena both as noise and as the real `../bin/GHOST.DAT`, and the object and
room tables are run BOTH as `init_globals` left them and as fuzz.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10efe` | `clear_physical_screen` | 34 | ✅ verified | run to `rts`; 3 seeds x noise over both screens, poison, and 4 overlapping-screen layouts |
| `0x131f0` | `present_score_strip` | 52 | ✅ verified | as above — the band, not the row: a start at +0x6400 instead of +0x6540 reddens 7 cases |
| `0x13224` | `present_hud_row` | 52 | ✅ verified | as above |
| `0x13258` | `stage_to_work` | 46 | ✅ verified | as above; the source/destination swap reddens 7 |
| `0x13286` | `present_room` | 102 | ✅ verified | as above; unrolled 32 longs x 200 in the original, one loop here |
| `0x1369a` | `draw_tile_bank_screen` | 120 | ✅ verified | run to `rts`; all 7 banks over noise, banks 0..5 over the real GHOST.DAT, poison |
| `0x13712` | `draw_hud_row_tiles` | 92 | ✅ verified | run to `rts`; noise + poison + the real tiles 350..359, and the arithmetic pin that its `add.l #$6400` is 50 tiles and not the room's byte size |
| `0x1376e` | `objects_animate_and_draw` | 510 | ✅ verified | run to `rts`; all 36 shipped rooms over the real GHOST.DAT, 4 of them over noise, 96 fuzz cases in 4 shards, and the two word-edge branches (`blt` on the tile, `bne` on the countdown) the shipped tables never reach |
| `0x132ec` | `build_sprite_bank` **(slice** `[0x132ec, 0x13330)` **)** | 68 of 322 | ✅ verified | `stop_pc` at the head of the grab loop: `bank_index = 0`, `draw_tile_bank_screen`, and the GEOMETRY fields of both MFDBs — `width`/`height`/`wdwidth`/`standard`/`planes`, offsets 4..12. `MFDB_ADDR` (offset 0) is NOT in the slice: the grab loop writes it once per cell from the `c_malloc` it has just made, so it is part of the residual. **Residual:** the 60 `c_malloc` + `vro_cpyfm` grabs, and the `fd_addr` each of them stores |
| `0x13a08` | `draw_room_to_stage` **(slice** `[0x13a38, 0x13afa)` **)** | 194 of 278 | ✅ verified | one iteration of the 5 x 10 loop, entered with the frame's `-4(a6)`/`-2(a6)`: all 50 cells of a shipped room, one cell of every one of the 36 rooms, 80 fuzz cases in 4 shards, poison, and two `ext.l` wrap cases. **Residual:** the loop's `vq_mouse` per cell, and the loop scaffolding around it (read-verified) |
| `0x13b1e` | `room_wipe_in` **(slice** `[0x13b62, 0x13bda)` **)** | 120 of 204 | ✅ verified | each of the 40 steps entered on its own with `D7 = step`, plus the whole loop twice — over noise, and over a staging area the ORACLE composed with 50 real tile draws first. Plus the two steps the game's own loop never reaches, which are what pin the present's WORD-sized `dbf` counter against the `mulu`'s longword product: step 409 (64 longs presented, not 65,600) and step -1 (the full 65,536, on a low staging of its own). **Residual:** the three `sound_release_voice` calls and the `sound_play` around it |

**Not here, and it is a model gap rather than a choice.** `save_sprite_backgrounds` @ 0x1342e,
`draw_sprites` @ 0x134f6 and `restore_sprite_backgrounds` @ 0x135d2 are three `vro_cpyfm` pairs
each, and `os_gem_trap` refuses VDI opcode 109 — so an oracle run of any of them is a refusal, not a
wrong answer. They are the same gap the three slices above cut around, and closing it is one modeled
VDI opcode (plus a raster-copy model, which is image state and so cannot be a no-op).

**What the differential cannot see here.** Nothing in this subsystem traps, so there is no ledger to
compare — but also nothing off-image: every byte these routines write is memory the diff covers, and
the surface that would catch a regression is the image itself. The one thing outside it is the
*screen base*, which XBIOS answers and the model no-ops; a wrong `Setscreen` would leave every
routine here byte-perfect and the picture invisible (`docs/on-target-execution.md`).

**A staging decision worth reading before adding a case.** The seven banks are staged with GAPS
between them rather than packed, because 60 tiles of 512 bytes is exactly a bank: with the banks end
to end, `dat_bank[n / 60] + (n % 60) * 512` collapses to `dat_bank[0] + n * 512` for every n and the
`divs.w #$3c` split stops being observable. Measured — a reconstruction splitting at 59 tiles per
bank passed all 244 cases before the gap went in.

The gaps are also IRREGULAR (`test/test_blit.py`'s `BANK_ADDRESSES`, seven ordered addresses drawn
from one fixed seed), because a constant stride is still affine: at `BANK_BASE + index * 0x8000` a
candidate that computed a bank's address arithmetically — never loading `dat_bank[index]` out of the
image — matched every case. `test_the_staged_banks_are_separated_and_inside_the_arena` asserts both
properties, so neither can be tidied away.

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept, and
each **red**:

| mutation | what caught it |
|---|---|
| `room_wipe_in_step`'s presented-longword count computed in 32 bits instead of `loop_passes(…, COUNT_MASK_WORD)` | 2 cases — `test_room_wipe_in_step_counts_the_presented_longs_in_a_word` (step 409) and `…_at_the_word_boundary_presents_the_whole_counter` (step -1). Both were WRITTEN for this: the 40 steps the game itself uses are all far inside a word and every one of them passed the 32-bit version |
| `copy_longs_descending` walking UP instead of down | 44 cases — the wipe's move onto its own overlapping span smears the other way |
| `TILES_PER_BANK` 60 → 59 | 85 cases — the `divs.w #$3c` bank split, which only the irregular gaps above make observable |
| `muls_ext_w` multiplying in 32 bits (no `ext.l`) | 3 cases — the two `test_draw_room_tile_offset_wraps_in_a_signed_word` rows and one fuzz shard |
| the object countdown's `!= 0` widened to `> 0` | 1 case — `test_objects_animate_and_draw_word_edge_branches`, which is the only thing that reaches a negative countdown |

Three earlier survivors, found on this battery's first pass and closed by the port agent, are the
reason three of those cases exist at all: a packed bank layout (closed by the gaps), a 32-bit
`muls_ext_w` (closed by the two wrap cases) and a `bgt` countdown test (closed by the word-edge
case). A mutation the suite does not catch is a coverage hole, not a licence — record it here.

## Verified — sound (12)

The whole engine between 0x142bc and 0x149b4: a five-call trigger API, the 200 Hz Timer C handler
that runs three voice records' worth of envelopes and LFOs, and the `trap #9` gate ordinary code
reaches the chip through. `../notes/sound_engine.md` is the design doc, `include/sound.h` the frozen
record layout. **There is no music and no sequencer** — 11 fixed effects and 36 per-room tones, each
one one-shot voice record.

**The chip is off-image, so most of what this subsystem does is invisible to the byte diff.** Every
row below therefore rests on two more surfaces than an ordinary one: the kit's ordered direct-PSG
ledger, which carries reads as well as writes (TRAP_MODEL.md, Phase 6), and — for the installer —
the hardware WRITE ledger (Phase 10). A reconstruction that made no chip access at all is
byte-for-byte identical to one that makes every access the original makes.

**Still unported in this subsystem:** the digitised-voice path (`load_voice_player` @ 0x13c6c,
`play_voice` @ 0x13cea, `GHOST.LOA`), which is a second program `jsr`ed inside the BSS and has
nothing to do with the engine here — it programs MFP Timer A and busy-waits, so it needs the model
gap named in "Model gaps" closed first.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x142bc` | `sound_play` | 520 | ✅ verified | all 47 shipped definitions x 3 voices; notes 0..127 plus the negatives and the fold's two boundaries; the priority refusal; the zero-duration "just stop it"; tone-off/noise-off; the volume argument and the no-envelope path; the DEAD voice allocator driven with synthetic voice args (free-scan over all 8 busy subsets, eviction over all 125 priority triples); 8 x 10 fuzz cases (chunk-SEEDED, so each shard draws its own) over synthetic definitions and random records. Accumulator zeroing pinned under the poison pass |
| `0x144c4` | `sound_stop_voice` | 76 | ✅ verified | the range check at -1/0/1/2/3 and both word extremes, over random records; the `psg_gate(8+v, 0)` write and its read-back compared in the PSG ledger |
| `0x14510` | `sound_release_voice` | 78 | ✅ verified | live and idle voices x the range check; duration := 1 and gate := -1 are the whole effect, and `test_isr_key_off_*` is what shows the handler then keys off on the next tick |
| `0x1455e` | `sound_voice_priority` | 24 | ✅ verified | voices 0..2, and 371/372/400/743 — the indices that make `muls.w`+`adda.w`'s sign-extended low word reach BELOW the record array, which is what separates this routine's arithmetic from a 32-bit add. Return compared against the oracle's D0 low word |
| `0x14576` | `sound_stop_all` | 36 | ✅ verified | four random three-record states; composes the verified `sound_stop_voice` |
| `0x1459a` | `timer_c_sound_isr` | 848 | ✅ verified | entered directly (it never `rte`s — it pushes TOS's saved `$114` and `rts`es, so the case stages that vector) and, for the multi-tick cases, through an 18-byte `dbf` stub that calls it N times in ONE oracle run. Covers: the idle skip and the conterm restore over all 8 busy subsets; the ADSR's five phases x four step signs; the triangle LFO folding at both limits with and without the onset delay; the three-segment pitch sweep both directions per segment; the pitch LFO's carry-driven step reload; the noise machine and its `cmp.b #$1f` on a word; the `muls.w` alias above a full-scale accumulator; the unbounded volume-scale index; the byte-wide phase compare; key-off over 18 phase/step combinations; a non-negative gate never counting down; the pointers being read out of the ISR state block (record base relocated); 8 x 10 chunk-seeded random-record fuzz cases at 1..8 ticks, and all 47 real definitions at 12 ticks (those PARTITIONED eight ways, `abi.shard`) |
| `0x148ea` | `install_sound_vectors` | 50 | ✅ verified | three (saved `$114`, conterm) pairs over a seeded state block. The two vectors and the four saved fields are image bytes; **`$fffffa17 := $40` is not**, and the hardware WRITE ledger is the only surface that sees it |
| `0x1491c` | `remove_sound_vectors` | 22 | ✅ verified | two saved states; the same ledger for `$fffffa17 := $48`. Pins that the `trap #9` vector is deliberately NOT restored |
| `0x14940` | `psg_gate` | 16 | ✅ verified | the user-mode stub, entered with its three argument words on the stack; the oracle takes the real `trap #9` through the `$a4` vector the case stages (which is the longword `install_sound_vectors` itself writes) |
| `0x14950` | `trap9_psg_handler` | 50 | ✅ verified | reached through `psg_gate` above — a direct entry is not runnable, because it ends in `rte` and the harness's frame is a `jsr`'s. All 16 registers written and read back; register 7's read-modify-write over 25 (value, mask) pairs; the negative-value pure read; the four-bit select mask; 8 x 12 chunk-seeded fuzz cases over the whole argument space with a fully declared chip. Return compared as a whole longword |
| `0x14982` | `sound_start` | 26 | ✅ verified | three caller register files. `Supexec` runs the installer nested in the oracle; the `xbios_trap` trampoline's three save slots are part of the diff, which is why a1/a2 are arguments |
| `0x1499c` | `sound_stop` | 26 | ✅ verified | two caller register files; the trap #9 vector has to be staged because `sound_stop_all` runs BEFORE the installer would have written it |

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept, and
each **red**:

| mutation | what caught it |
|---|---|
| the pitch LFO's carry test inverted (`long_add_extend` → its negation) | 18 cases — `test_isr_pitch_lfo_reloads_its_step_on_a_carry` and the record fuzz. The carry is only reachable with the huge steps that case uses, which is why it exists |
| `PSG_REG_SELECT_MASK` 0x0f → 0x1f | 9 cases — `test_psg_gate_masks_the_register_number_to_four_bits`, through the PSG ledger's ordered select stream |
| the volume phase compared as a WORD instead of a byte | 10 cases — `test_isr_selects_the_phase_with_a_byte_compare`, whose high-byte phases `sound_play` really can copy out of a definition |
| the noise clamp's `cmp.b` widened to the word it tests | 10 cases — `test_isr_noise_machine_and_its_byte_wide_clamp`, at the 0x80/0x90 rows that slip past a byte compare |
| `sound_start` skipping its `trap_save_registers` | 1 case — `test_sound_start`, on the three trampoline save slots |

Two earlier survivors, found on this battery's first pass and closed by the port agent, are why two
of those cases exist: a word-wide phase compare (closed by the byte-compare case) and a widened
noise clamp (closed by the 0x80/0x90 rows). A mutation the suite does not catch is a coverage hole,
not a licence — record it here.

### Residuals — what these rows do NOT pin

Six, all of them off-image effects the differential has no surface for. None is a gap in the C; each
is a claim that would need a run on real hardware or a new kit surface to check.

1. **The handler's IPL drop.** `ori.w #$500,sr` / `andi.w #$fdff,sr` takes the entry IPL of 6 to
   exactly 5, so other MFP channels — the keyboard ACIA in particular — can nest inside the tick.
   That is a status-register effect with no image consequence, and the reconstruction does not
   express it at all. It is also what the installer's automatic-EOI mode exists for, so the two
   residuals are one fact.
   **THE SURFACE IS THE ON-TARGET SMOKE RUN** (`docs/on-target-execution.md`, "The observable
   surfaces"): an ISR that did not drop its IPL locks out the keyboard, so a .PRG that boots to the
   title and accepts a keypress with sound running is what would catch it. Nothing off target can,
   and this project has no .PRG yet — so the residual stands unpinned until it does.
2. **The chain, rather than an `rte`.** The handler ends by pushing TOS's saved `$114` vector and
   `rts`ing, so TOS's own Timer C work still runs. The cases stage that vector with the harness's
   sentinel (or, for a multi-tick run, a bare `rts`), which proves the handler jumps THROUGH it —
   but TOS's handler is not in the image and is never run. **The surface is the same on-target smoke
   run**: a chain that did not reach TOS stops the system clock and the keyboard repeat, which a
   booted .PRG shows and a byte differential cannot.
3. **`trap9_psg_handler` parks the select latch on register 11** (`move.b #$b,(a0)`) so nothing is
   left pointing at the I/O ports. **The surface is a THIRD PSG event kind in the kit's ledger** — a
   bare *select* with no access — which `psg.h` does not have: its calls select and access together,
   so neither side can record one and the two agree by construction. Adding `psg_port_select(reg)`
   and a `SELECT` entry to the ordered ledger is the whole change, and it is a kit change; until it
   lands the final latch position is unverified on both sides rather than verified on neither.
4. **`psg_gate`'s `mask` argument is stack garbage at four of its six call sites**, which push only
   two argument words. The reconstruction passes a definite 0. It is never read at those sites (the
   handler consults `mask` only for register 7, and none of the four selects register 7), so this is
   sound rather than merely convenient — but it is a claim about the handler, not something a case
   observes.
5. **`sound_start`/`sound_stop` take the caller's a1/a2 as arguments** (`docs/agent-playbook.md` §5,
   "a parameter"). The `xbios_trap` trampoline files whatever the register file holds and nothing in
   these two routines computes it; the cases take the values FROM the oracle's own input registers.
   Closing it means porting the callers.
6. **The `short` return values are compared as D0's LOW WORD.** That is the Alcyon C ABI's answer
   and what every caller reads; D0's high half is whatever the routine's own arithmetic left there.
   `psg_gate` is the exception and is compared whole, because it answers with a zero-extended byte.

## Verified — clib (32)

The Alcyon/DRI C runtime linked into the program, `src/clib.c` / `include/clib.h` / `test/test_clib.py`.
Ported in dependency order: the string and 32-bit arithmetic leaves, the fd-mode side table, the
free-list allocator, the low-level file layer and the whole software floating-point package — and
with them the two OS trap trampolines, which are verified through the wrappers that call them.

**Three shapes of evidence**, because most of this subsystem answers somewhere the byte diff cannot
see. A routine whose answer is D0 is checked against the oracle's D0 as well as by the image diff.
`c_ldiv` and `c_lmul` answer through their CALLER'S argument slots, which lie in the band the
differential drops as stack — those run from a poked stub (`test/abi.py`'s `c_call_pokes`) that
files the answers at `abi.RESULT`. And the trap trampolines' only reproducible effect is the three
save slots, so every case that traps stages noise over them: the `RET_*` value a wrapper leaves says
WHICH trap site ran, which is what tells a binary `c_read` (one Fread) from a text one (several).

**The floating-point package is byte-compared, never float-compared.** It keeps a 32-bit mantissa
where an IEEE double has 53, so "the same number in Python" and "the same eight bytes" are different
questions and only the second is asked. Half the fuzz's operands are raw 64-bit patterns rather than
doubles Python would name — the package has no special case for an infinity, a NaN or a denormal (a
zero EXPONENT is the only value it tests for), so those are ordinary inputs to it.

**279 cases.** The fuzzes are CHUNK-SEEDED rather than chunk-partitioned (`test/abi.py`'s `shard`
docstring tells the two apart), so each is `CHUNKS` x its own per-chunk count: the ldiv/lmul fuzz is
8 x 24 pairs through each routine, the allocator fuzz 8 x 16 arenas, the arithmetic fuzz 8 x 24
operand pairs and the conversion fuzz 8 x 24 patterns through each of three routines. `make guarded`
sweeps the same suite clean — the allocator indexes the image with addresses it computes, so that is
its surface.

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept. The
first sweep (granule size, the two rounding increments, the mantissa shift, the binary-mode bit,
fp_add's shift bound, the CR constant, c_free's wrap test, the refill's return address, fp_mul's
sticky bit, fp_div's step count, c_ldiv's sign tally, c_getfdmode's overrun) reported 12/12 killed;
re-running the rounding-increment one under the errno/zero-divisor work below found that it does not
in fact die, so eleven of those twelve stand and the twelfth is recorded as a hole. The second sweep:

| mutation | result |
|---|---|
| `c_ldiv` loses its zero-divisor branch | **red** — `test_c_ldiv_by_zero_stores_zero_over_both_slots` fails on `(0, 0)` and does not terminate on `(0, 5)`, which is the defect the branch closes: without it the C is not merely wrong but non-terminating |
| `c_close` drops its `errno` store | **red** (2 cases) — only since `fd_table_poke` began seeding `A_c_errno` with NOISE; before that the store wrote a 0 over a 0 and the mutation survived the whole suite |
| `c_read` drops its closing `errno := 0` | **red** (3 cases) — the same noise seeding |
| `fp_div`'s `long_sub_extend` borrow made inclusive (`<=`) | **red** (3 cases) |
| `fp_float_to_double`'s `and.l #$8fffffff` widened to `#$9fffffff` (three sign-fill bits → two) | **red** (11 cases) |
| **`fp_pack_float` rounding with the DOUBLE's increment (0x100 instead of 0x200)** | **SURVIVES — and cannot be caught.** See "a hole with a proof" below |
| `c_read` drops its ENTRY `errno := 0` | **SURVIVES.** See below |

**A hole with a proof.** `fp_pack_float`'s `add.l #$200,d2` is transcribed correctly, but no case can
tell it from the double's `#$100`. The round only runs when the guard bit 0x100 is set, and the tail
then stores `mantissa >> 9`. Write `m = 512q + r`: the guard being set means `r >= 256`, so
`(m + 0x100) >> 9 = q + 1 = (m + 0x200) >> 9` for every such m, and the two increments carry out of
bit 31 on exactly the same inputs (bit 8 set puts m either in the range where both carry or the range
where neither does), so the exponent and the re-round follow identically. The differing bit is shifted
out before it is stored. It is unpinnable through this routine's bytes, not merely unpinned — and
`fp_pack_float` has no caller in the program, so there is no composition that would expose it either.

**And a second one, for the same reason: no surface.** `c_read` opens `wr16(A_c_errno, 0)`, and every
path out of it writes `A_c_errno` again before returning — the count after the first Fread, then 0 at
the exit, on the binary path and the text path alike. The entry store is therefore invisible in the
final image, which is all the differential compares; the write LEDGER would see it, but the harness
compares final memory rather than write sequences. Transcribed and left honestly unpinned.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x1683e` | `c_strlen` | 41 | ✅ verified | 5 strings incl. empty and 199 bytes; D0 compared as a longword |
| `0x167fc` | `c_strcmp` | 66 | ✅ verified | 10 pairs incl. three high-bit ones — the bytes are SIGN-extended, so an unsigned port returns the opposite sign |
| `0x158fe` | `c_ldiv` | 114 | ✅ verified | stub-driven; 10 edge pairs with attribution poison + 8 x 24 fuzz pairs. Both answers land in the caller's slots. The ZERO DIVISOR is three more cases, run with the machine's zero-divide vector declared (see the residual), plus one that pins the oracle refusing the run without it |
| `0x15970` | `c_lmul` | 108 | ✅ verified | stub-driven; 11 edge pairs with poison + 8 x 24 fuzz pairs. It eats four of its own eight argument bytes |
| `0x15cae` | `c_setfdmode` | 76 | ✅ verified | 5 tables incl. a FULL one, where the record is silently dropped |
| `0x15cfa` | `c_clearfdmode` | 60 | ✅ verified | 5 handles over a table holding one twice — both copies are cleared |
| `0x15d36` | `c_getfdmode` | 46 | ✅ verified | 4 handles, one of them ABSENT: the miss reads past the table onto `A_c_malloc_freelist`, staged with random bytes so a plausible 0 would fail |
| `0x15e58` | `gemdos_trap` | 28 | ✅ verified | through every wrapper below: the three save slots are staged with noise and diffed, and the `RET_*` says which site ran |
| `0x15e3c` | `xbios_trap` | 28 | ✅ verified | entered directly with XBIOS Physbase (0x02); D0 = `OS_SCREEN_BASE` and the slots hold the harness's own sentinel |
| `0x15c82` | `gemdos_malloc` | 22 | ✅ verified | 6 sizes; D0 = the modeled arena base, plus the save slots |
| `0x15c98` | `gemdos_mfree` | 22 | ✅ verified | 3 blocks; Mfree always succeeds and frees nothing |
| `0x167c8` | `gemdos_malloc_or_fail` | 52 | ✅ verified | 4 sizes; the 0 -> -1 arm is unreachable under the model (see the residual) |
| `0x15af2` | `c_morecore` | 98 | ✅ verified | 5 granule counts across the quantum boundary; the c_free that links the new block in is part of the diff |
| `0x15b54` | `c_malloc` | 170 | ✅ verified | an EMPTY list (self-init + morecore), 7 sizes over a six-block arena, and roughly half of the 8 x 16 fuzz arenas (the arm is a coin, and the case asserts both arms ran) |
| `0x15bfe` | `c_free` | 130 | ✅ verified | 6 (victim, roving-pointer) combinations + the other half of the 8 x 16 fuzz arenas — both coalescing arms and the list's wrap. Every fuzz arena now carries at least one ALLOCATED block, so the free arm can no longer skip itself |
| `0x15d64` | `c_open` | 214 | ✅ verified | 4 modes on a staged file + the three pseudo-devices, which never reach GEMDOS |
| `0x14c7a` | `c_creat` | 154 | ✅ verified | 2 modes (Fcreate truncates the staged file) + the CON: path, which tail-calls c_open |
| `0x14c3c` | `c_close` | 62 | ✅ verified | 2 real handles and 2 pseudo-handles; the signed word compare against 0x8300 is what separates them |
| `0x1667c` | `c_read` | 332 | ✅ verified | 5 binary lengths + 5 text ones. The text pass drops CRs and TOPS THE BUFFER UP, so its later Freads leave a different `RET_*` and a different A2 |
| `0x15394` | `fp_pack_double` | 106 | ✅ verified | entered DIRECTLY as the tail it is (A6 names the frame it unwinds); 9 (mantissa, exponent) pairs across the normalise, round-to-even and carry-out arms, plus every add/sub/mul/div case, which all end here |
| `0x15132` | `fp_pack_float` | 90 | ✅ verified | 7 pairs, entered at the `link a6,#$0` stub. NOTHING IN THE PROGRAM CALLS IT (see the residual) |
| `0x15552` | `fp_long_to_double` | 50 | ✅ verified | 13 longwords incl. both extremes + 8 x 24 random patterns |
| `0x154d0` | `fp_float_to_double` | 58 | ✅ verified | 8 singles + 8 x 24 random patterns; the 64-bit `asr/roxr` triple is the shape a port gets wrong |
| `0x1550a` | `fp_double_to_long` | 70 | ✅ verified | 20 doubles + 8 x 24 random patterns; the shift count is taken mod 64 as the 68000 takes it |
| `0x154b0` | `fp_acc_load_long` | 16 | ✅ verified | 7 longwords in D0, widened in place at `A_fp_acc` |
| `0x154c0` | `fp_acc_to_long` | 16 | ✅ verified | 20 accumulator values; D0 compared as a longword |
| `0x152fa` | `fp_add` | 154 | ✅ verified | 11 edge pairs + its share of the 8 x 24 chunk-seeded fuzz pairs; shares its body and its exit with fp_sub |
| `0x152e0` | `fp_sub` | 26 | ✅ verified | same battery: it flips the SOURCE's sign word in memory and the shared body flips it back |
| `0x1524e` | `fp_mul` | 144 | ✅ verified | 11 edge pairs + its share of the 8 x 24 chunk-seeded fuzz pairs; three 16x16 partials and a sticky bit for the fourth |
| `0x151d0` | `fp_div` | 126 | ✅ verified | 11 edge pairs + its share of the 8 x 24 chunk-seeded fuzz pairs; 32 restoring-division steps over a 64-bit remainder |
| `0x15190` | `fp_cmp` | 66 | ✅ verified | 9 pairs; its ONLY output is `A_fp_ccr`, the whole SR — see the residual on its high byte |
| `0x153fe` | `fp_dispatch` | 178 | ✅ verified | 5 double-source opcodes + 6 widening ones, plus the whole `Random() -> 5..15` chain the front end computes, run as five C calls from one stub |

### What the demo-range chain now rests on

`test_demo_slideshow_length_chain` runs `fp_acc_load_long` → `fp_dispatch(0x803, /16794009)` →
`fp_dispatch(0x802, *11)` → `fp_dispatch(0x800, +5)` → `fp_acc_to_long` as one differential and
asserts the 5..15 the plate at 0x115d6 in `../names.txt` claims, with both boundaries pinned
(`Random()` = 0 gives 5, `Random()` = 0xffffff gives 15 and never 16). That plate's reasoning is now
executed rather than argued.

### Residuals — reconstructed, not covered by a case

* **`c_ldiv` with a zero divisor executes `divu.w #0,d0` deliberately** — the library's way of
  raising the 68000's zero-divide exception — and then answers 0/0 from `clr.l d0 / clr.l d1`. THIS
  IS NOW A VERIFIED BRANCH, not a residual, and it took a measurement off real TOS to make it one:
  a GEMDOS program run headless under Hatari on the TOS ROM reports vector 5 (`$14`) = `$e00d68` and
  comes back from a user-mode `divu.w #0` with D0 untouched — so the handler RETURNS and the
  library's own continuation is what the machine executes. The harness's image has no such vector
  (`$14` is zero, and the oracle takes the exception into the vector page), so the three cases
  DECLARE the machine by poking an `rte` at `$14`, and a fourth pins that the declaration is
  load-bearing: without it the oracle refuses the run. What remains unpinned is only the identity of
  TOS's handler — the cases run an `rte`, TOS runs `$e00d68`, and nothing in the image could tell
  them apart. The probe itself was a one-off (`tos_probe.run_tos_program`); it is not in the suite,
  because a 20-second Hatari boot in a 2-second `make test` would be the wrong trade.
* **`c_ldiv` with a divisor of 0x80000000 HANGS.** Its magnitude cannot be represented, so `neg.l`
  leaves it negative, the alignment loop shifts the 1 out of the top and never reaches
  `divisor >= dividend` again. The original's own behaviour, transcribed; the fuzz keeps both
  magnitudes below 0x40000000 and says so.
* **`gemdos_malloc_or_fail`'s failure arm (Malloc returned 0 → -1) is unreachable**: the modeled
  Malloc is a bump allocator that always succeeds. Read-verified, as is `c_morecore`'s and
  `c_malloc`'s handling of it.
* **`c_open`'s and `c_creat`'s "GEMDOS refused" arms are unreachable** for the same kind of reason:
  `os_fopen` REFUSES an unstaged name rather than returning a negative handle, so a case that asked
  for one would be rejected instead of exercising the arm. Read-verified.
* **`c_open`'s truncating arm (`mode & 1`) calls `c_unlink` @ 0x16868 = GEMDOS Fdelete**, which the
  kit does not model. The reconstruction routes it through `os_refused`, so a case reaching it fails
  loudly. Nothing in the game asks for it — `c_creat` requests write access only.
* **`c_read`'s console arm** (a handle at or below `FD_DEVICE_CON`, served by `c_conin` @ 0x16518)
  is not reconstructed at all: its body is GEMDOS Crawcin/Cnecin. It refuses.
* **`fp_cmp`'s `status_high` is a harness fact, not a reconstruction's output.** The routine stores
  the WHOLE status register, whose high byte is the machine's mode and interrupt mask; the battery
  declares it (0x2700) and every fp_cmp case would redden if it were wrong, but no reconstruction
  could derive it.
* **`fp_pack_float` @ 0x15132 has no caller.** It is `fp_op_table[6]` and all four of the program's
  `fp_dispatch` sites carry opcodes 0x0800..0x0804. It is reconstructed and verified anyway, entered
  at its own stub, because it is real code in the shipped binary.
* **`fp_dispatch` selects among the seven operations with a `switch`, not an indirect jump.** The
  table is `init_globals`' output and never written again; `test_fp_op_table_points_where_the_
  reconstruction_assumes` reads all seven slots off the post-init image, follows each `jmp` island
  and pins the routine it lands on. Dispatching opcode 5 or 6 — the two packing TAILS, which pop ten
  saved registers and unlink a frame `fp_dispatch` never pushed — refuses instead of inventing a
  behaviour.
* **`fp_dispatch`'s widening scratch is its own stack local** (-10(a6)), inside the band the diff
  drops. Nothing compares those eight bytes directly; what pins the widening is the destination the
  widened value is then added to.

### Not ported, and what each would need

| Routine | Why | What would close it |
|---|---|---|
| `c_conout_write` @ 0x16b5e | GEMDOS Cconout is modeled as a NO-OP with no ledger, and the routine's only other effect is on its caller's stack. It has **no observable surface at all** | a console-output ledger in the kit, beside the Dosound one: an ordered list of the bytes each `Cconout`/`Cconws` was given, compared like `g_dosound_log_*`. Without it the same gap silently covers `c_write`'s CON: arm and the whole `c_printf` path |
| `c_write` @ 0x16c04, `c_putc` @ 0x150ee, `c_flsbuf` @ 0x14fb0, `c_filbuf` @ 0x14e80, `c_fflush` @ 0x14dc4, `c_fopen` @ 0x156e2, `c_fread` @ 0x15878, `c_fclose` @ 0x14d72 | the buffered FILE layer. Reachable and modelable (Fread/Fwrite/Fopen/Fclose all exist), but not yet read | ordinary porting work; the `c_iob` record is 20 bytes — ptr(l) cnt(w) base(l) flags(w) fd(w) offset(l) bufsiz(w) — read off the post-init image at 0x1eb08, stride 20, 73 entries |
| `c_printf` @ 0x164c2, `c_vfprintf` @ 0x16496, `c_sprintf` @ 0x164d8, `c_fputs` @ 0x164ee, `c_doprnt` @ 0x1620c, `c_fmt_integer` @ 0x15e74, `c_fmt_getnum` @ 0x161b8, `c_fmt_float` @ 0x15fe0, `c_fcvt` @ 0x15588 | the printf engine. `c_sprintf` and `c_doprnt` write into a caller buffer and need NO trap, so they are the natural next slice; the rest reach the FILE layer above | ordinary porting work. `c_printf` has exactly one call site in the game (main's LOW REZ message), so the engine's value is the format coverage, not the caller |
| `c_lseek` @ 0x159dc | GEMDOS **Fseek (0x42)**, unmodeled | the staged-file table already carries a cursor (`OS_FS_OFF_CURSOR`); Fseek is the one accessor of it the model never grew. Three whences and a negative-result re-probe |
| `c_unlink` @ 0x16868 | GEMDOS **Fdelete (0x41)**, unmodeled | clearing a staged slot's name (or its open flag) and answering 0/-1. One site, and only `c_open`'s truncating arm reaches it |
| `c_exit_pterm` @ 0x14d16 | GEMDOS **Pterm (0x4c)**, unmodeled and unmodelable as a return | nothing: a run that terminates has no `rts` to diff at. Record it read-verified |
| `c_exit` @ 0x14d2c | walks the 73 `c_iob` entries calling `c_fclose`, then Pterm | the FILE layer above, plus a `stop_pc` checkpoint at the Pterm call rather than a model for it |
| `c_conin` @ 0x16518 | GEMDOS **Crawcin (0x07) / Cnecin (0x08)**, unmodeled | a blocking read over the poked console state (`OS_CON_PENDING`/`OS_CON_CHAR`), beside the existing `Crawio`; and a decision about what a blocking read does with nothing pending |
| `c_auxout_write` @ 0x16ba8, `c_prtout_write` @ 0x16bd6 | GEMDOS **Cauxout (0x04) / Cprnout (0x05)**, unmodeled — and like `c_conout_write` they would have no image effect if they were | the console-output ledger above, extended by device |

## Borrowed globals

A global lives in the header of the subsystem that owns the data (README.md, "Adding a function").
A row here is a LOAN: a global defined in a header that does not own it, because the routine that
does is unported. Each row names the address, the name as spelt, the owner, where it is defined
today, and why — and a finished migration DELETES its row and the `#define` it names, so the
table's length reads as outstanding debt rather than as history.

| Addr | Name | Owner | Defined in | Why on loan |
|---|---|---|---|---|
| `0x23120` | `A_room_number` | gameplay | `include/blit.h` | `objects_animate_and_draw` and `draw_room_to_stage` both index their table by it, and the room loop that WRITES it (`game_top_loop` @ 0x101e6) is unported |
| `0x2069a` | `A_object_table` | gameplay | `include/blit.h` | the animator steps the records; the `OBJECT_*` field offsets in `include/blit.h` move with this row |
| `0x21a4a` | `A_room_table` | gameplay | `include/blit.h` | the stage draw reads the tile map out of it; `ROOM_STRIDE` / `ROOM_MAP_ROW_BYTES` move with this row |

**THE THREE ROWS ABOVE ARE THE ONES LIKELY TO CLASH NEXT.** The moment `include/gameplay.h` names
any of those addresses, `test/test_constants.py::test_no_constant_is_defined_in_two_files` (or
`::test_no_address_has_two_spellings`, if the name differs) goes red in the OTHER agent's diff —
and this row is how they find the edit to make: delete the `#define` and its BORROWED note from
`include/blit.h`, add `#include "gameplay.h"` to `src/blit.c`, and delete the row.

**What the two checks do and do not cover, for the `OBJECT_*` / `ROOM_*` record offsets that move
with those rows.** A record offset re-defined under the SAME name in `include/gameplay.h` IS caught
— `test_no_constant_is_defined_in_two_files` is keyed on the name and takes offsets as readily as
addresses. What is NOT caught is the same offset under a DIFFERENT name: `OBJECT_TILE` here and,
say, `OBJ_TILE_INDEX` there, both 0. `test_no_address_has_two_spellings` is value-keyed but only over
the `A_*` family, deliberately — for geometry and record offsets a shared VALUE carries no
information at all (`OBJECT_TILE` and `MFDB_ADDR` are both 0 and always will be), so a value-keyed
check over these families would fire on coincidences and be turned off. So the differently-named
duplicate is the case that has to be caught by reading, and the provenance tag on every `OBJECT_*` /
`ROOM_*` line in `include/blit.h` — the `lea`/`muls` instruction each offset was read off, and the
case that pins it — is what makes that reading cheap.

## Not reconstructed, and why

Every `fn` line in `../names.txt` with no ✅ row above eventually appears here, with the reason:
unreachable under the model, a model gap named above, or simply not yet started. The three ported
sections each deferred a named set; those sets are gathered here so that "what is left" is one list
rather than three asides.

| Routine(s) | Subsystem | Why not, and what would close it |
|---|---|---|
| `save_sprite_backgrounds` @ 0x1342e, `draw_sprites` @ 0x134f6, `restore_sprite_backgrounds` @ 0x135d2 | blit | Three `vro_cpyfm` pairs each, and `os_gem_trap` refuses VDI opcode 109 — an oracle run of any of them is a REFUSAL, not a wrong answer. Closing it is one modeled VDI opcode plus a raster copy (image state, so it cannot be a no-op). The same gap is what the three blit SLICES cut around |
| `load_voice_player` @ 0x13c6c, `play_voice` @ 0x13cea | sound | The digitised-voice path (`GHOST.LOA`): a second program `jsr`ed inside the BSS that programs MFP Timer A and busy-waits. Needs the timer/busy-wait gap in "Model gaps" closed first; it has nothing to do with the engine that IS ported |
| `c_conout_write` @ 0x16b5e, `c_auxout_write` @ 0x16ba8, `c_prtout_write` @ 0x16bd6 | clib | GEMDOS Cconout/Cauxout/Cprnout are modeled as no-ops with no ledger, so these routines have **no observable surface at all**. A console-output ledger in the kit, beside the Dosound one, is what would give them one — see the per-routine table in the clib section |
| `c_write` @ 0x16c04, `c_putc` @ 0x150ee, `c_flsbuf` @ 0x14fb0, `c_filbuf` @ 0x14e80, `c_fflush` @ 0x14dc4, `c_fopen` @ 0x156e2, `c_fread` @ 0x15878, `c_fclose` @ 0x14d72 | clib | The buffered `FILE` layer. Reachable and modelable — ordinary porting work, not a gap |
| `c_printf` @ 0x164c2, `c_vfprintf` @ 0x16496, `c_sprintf` @ 0x164d8, `c_fputs` @ 0x164ee, `c_doprnt` @ 0x1620c, `c_fmt_integer` @ 0x15e74, `c_fmt_getnum` @ 0x161b8, `c_fmt_float` @ 0x15fe0, `c_fcvt` @ 0x15588 | clib | The printf engine. `c_sprintf` and `c_doprnt` need no trap and are the natural next slice |
| `c_lseek` @ 0x159dc, `c_unlink` @ 0x16868, `c_conin` @ 0x16518, `c_exit_pterm` @ 0x14d16, `c_exit` @ 0x14d2c | clib | One unmodeled GEMDOS call each (Fseek, Fdelete, Crawcin/Cnecin, Pterm) — the clib section's table says what each would need |
| everything in `init`, `frontend` and `gameplay` | — | Not started. The boot chain (`crt0_start`, `init_globals`, `main`, `init_video_and_heap`, `game_top_loop` — every one a slice rather than a function, see that section); the presentation, menu, demo playback and hall of fame; the bubble, the fans, the collision and the room logic |
