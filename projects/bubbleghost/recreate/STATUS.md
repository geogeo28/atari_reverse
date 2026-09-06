# Reconstruction status — Bubble Ghost

Human-readable C reconstruction of Bubble Ghost (ERE Informatique, 1987), each function **verified
byte-for-byte against the original 68000 code** by the shared differential harness
(`tools/recreate_kit`: a Musashi oracle running the real code vs. the compiled reconstruction, on
the same memory image). `../names.txt` is the source of truth for every name.

**Verified: the sum of the per-section counts below**, out of the **134** functions Ghidra found in
this program (`../notes/anchors.md`, "Shape of the image" — that is the whole code segment: the
31 KB running to the end of TEXT is `init_globals`' own instruction stream, not undiscovered code).
Five of the six sections carry rows today — `blit`, `sound`, `clib`, `gameplay` and
`frontend`. `init` is still a heading waiting for its first function.
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

**The skeleton's own gates are 33 tests** — `test_image_model.py` 22, `test_constants.py` 6,
`test_status.py` 5 — with each battery's cases on top of them, so the suite total is not a number
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
| ~~**GEMDOS `Cconis` (0x0b), 6 sites**~~ **CLOSED** | every keyboard poll — the menu's "Press [G]…[P]…[D]…[H]", the pause | TRAP_MODEL.md Phase 13 models it over the poked console state, beside `Bconstat`. No routine here uses it yet: the menu is unported |
| ~~**GEMDOS `Crawcin` (0x07), 7 sites / `Cnecin` (0x08), 4 sites**~~ **CLOSED** | the same keyboard paths, on the blocking side | Phase 13 models both, over the same one QUEUE every console read takes from (`harness.console_keys`, up to eight deep); a blocking read with nothing staged REFUSES rather than fabricating a key |
| ~~**GEMDOS `Fseek` (0x42), 5 sites**~~ **CLOSED** | reached only through `c_lseek` @ 0x159dc, which neither hall-of-fame routine calls: both read and write GHOST.SCR sequentially | Phase 13 models it over the staged-file cursor, with a refusal rather than an error code for a seek the model cannot serve |
| **GEMDOS `Fdelete` (0x41) / `Pterm` (0x4c) / `Cauxin` (0x03) / `Cauxout` (0x04) / `Cprnout` (0x05), 1 site each** | the C library's own wrappers (0x16868, 0x14d16, 0x16666, 0x16bae, 0x16bdc) — `clib` work, almost certainly unreachable in play | nothing, until someone ports those wrappers. Record them read-verified rather than growing the model for a path the game never takes |
| ~~**BIOS `Bconout` (trap #13), 2 sites**~~ **CLOSED** | `game_top_loop` @ 0x101e6 only: the IKBD commands `$12` (disable the mouse) and `$08` (relative reporting back on) | Phase 13 models device 4 as an OS EVENT LEDGER entry per byte and refuses every other device. No routine here uses it yet: `game_top_loop` is unported |
| ~~**`trap #2` (GEM), 2 trampolines**~~ **CLOSED** | the AES one @ 0x149b6 (`d0 = $c8`) and the VDI one @ 0x168d4 (`d0 = $73`) | Closed by TRAP_MODEL.md phases 11-13: the kit now models an ST raster, `vro_cpyfm`'s sixteen logic operations, and every VDI/AES opcode this game uses (VDI 3, 8, 12, 22, 25, 100, 109, 114, 124, 128; AES 10, 77, 78). Both trampolines and all sixteen entry points are verified in `## Verified — frontend` |
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

The boot chain: `crt0_start` @ 0x10036, `init_globals` @ 0x16d8e, `main` @ 0x100dc and
`game_top_loop` @ 0x101e6. Every one of them is a slice rather than a function — the loop never
returns — so each row's Verification column opens with the `[start, end)` the differential actually
runs.

**`crt0_setup_args` @ 0x10116 is not here either, and it IS reconstructed.** The crt0 calls it
(`pea 128(a0) / jsr $10116`) and it is a bare `rts` — the Alcyon runtime's argv hook, stubbed out at
link time. It belongs to the C library rather than to this game's boot chain, so its row is in
`## Verified — clib`.

**`init_gem_and_screens` @ 0x10118 is NOT here**, though the boot chain calls it: it opens the AES
connection and the VDI workstation and takes both screen bases off XBIOS, which is the front end's
binding end to end, so it is verified in `## Verified — frontend` with the routines it is made of.
`init_globals` is likewise not a boot-chain row waiting to be written — `test_image_model.py`
already runs it under the oracle and proves the image it leaves equal to the real crt0's.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|

## Verified — frontend (33)

**The GEM binding, and everything the rest of this project was cut around.** Bubble Ghost is a GEM
application: it opens a virtual workstation and draws its text, its bonus bar and its 32x32 sprites
through the VDI (`../notes/frontend.md` §1). The twelve VDI entry points and four AES ones below,
plus the two trampolines under them, ARE that binding, and porting them is what closes the three `src/blit.c` slices, the
`vro_cpyfm` residuals and (for whoever ports them) the HUD painters. `include/frontend.h` has the
two parameter blocks and every record; `src/frontend.c` is one file of wrappers plus the boot-time
setup, the sprite protocol and the file loaders.

**What replaces `trap #2`.** The oracle really executes the trap and `shim.c` services it out of the
kit's GEM model; the reconstruction calls that same model — `os_vdi` / `os_aes` — over the same
parameter block at the same address in the same image (TRAP_MODEL.md, phases 11-13). One
implementation, one block: what the VDI draws is image state on both sides, so the byte diff covers
the pixels — and the one call here with no image effect at all, `graf_mouse`, is compared as the
ordered OS event ledger instead.

**Every routine here takes the caller's A1/A2** — both trampolines park them and nothing in the
routine computes them (`docs/agent-playbook.md` §5, "a parameter") — and `init_gem_and_screens`,
`load_hiscores` and `draw_hall_of_fame` also take their own A6, because each hands a callee the
address of a stack local and a C reconstruction has no machine stack. Those locals lie in the band
the differential drops, so the frame is an input both sides are handed.

**The three sprite routines MOVED HERE from `src/blit.c`'s residual list**, and the reason is
ownership rather than reach: `save_sprite_backgrounds`, `draw_sprites` and `restore_sprite_backgrounds`
are three `vro_cpyfm` pairs each, so they belong with the sprite protocol and the binding that
carries it, not with the raw `move.l` blitters. `build_sprite_bank`'s grab loop and
`draw_room_to_stage`'s per-cell `vq_mouse` are the same story: each is the residual `src/blit.c` cut
its slice around, and each is closed here by COMPOSING that file's verified core rather than
restating it. The A2 the tile draw leaves used to be the one exception — this file re-derived it —
and is not any more: `draw_room_tile_to_stage` REPORTS it, and the per-cell slice compares the
answer against the oracle's own A2.

**THE INPUT BLOCK IS THIS SUBSYSTEM'S NOW, and "Borrowed globals" is five rows shorter.**
`A_key_raw`, `A_key_shift_state`, `A_mouse_y`, `A_mouse_x` and `A_mouse_buttons` are the five words
`vq_mouse` @ 0x16a26, `vq_key_s` @ 0x16a5e and the `Crawio(0xff)` poll fill; they were on loan in
`include/gameplay.h` while this binding was unported, and they are defined in `include/frontend.h`
now. `src/gameplay.c` includes that header to read them — the migration the loan table predicted,
made. `A_sound_enabled` was NOT part of it and its row is gone for the opposite reason: the routine
that writes it is `game_frame_update`'s `^S` arm, which is the gameplay subsystem's, so gameplay owns
it and never borrowed it.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10118` | `init_gem_and_screens` | 206 | ✅ verified | run to `rts` from a machine holding none of its state: `appl_init`, `graf_handle`, `v_opnvwk`, both `Getrez`/`Logbase` calls and the `Super` pair round the conterm write. Plus a second case reading the result off the oracle — the two screens a screen apart, the resolution the model answers, the cleared conterm byte and a non-zero `Super` cookie |
| `0x10dea` | `load_demo` | 90 | ✅ verified | run to `rts` over the real `../bin/GHOST.DEM`, plus a case that reads the two pointers back and pins the cursor parked on the base with the file's first record under it |
| `0x10e44` | `load_presentation` | 116 | ✅ verified | run to `rts` over the real `../bin/GHOST.PRE`, whose 0x7820 bytes are exactly the picture and the palette behind it |
| `0x10eb8` | `show_presentation` | 70 | ✅ verified | run to `rts` over the real GHOST.PRE tiles, with poison. Composes `draw_tile_bank_screen` and `clear_physical_screen` (`src/blit.c`) and files the `Setpalette` trampoline's three save slots |
| `0x11d6e` | `hiscore_submit_players` | 78 | ✅ verified | run to `rts` in both player counts and on both sides of the insert: five cases, the last two of which insert once and twice, so the whole chain down to the file write runs |
| `0x11dbc` | `draw_hall_of_fame` | 456 | ✅ verified | run to `rts` over three tables incl. an all-zero one: room 0 as the backdrop, five fixed labels, and the five rows drawn from slot 4 DOWN so the best entry lands on the "SCORE 1:" row. Every glyph is on the declared screen, so the diff compares the picture. Composes `draw_room_to_stage`, `stage_to_work` and `itoa_padded` |
| `0x11f84` | `hiscore_insert_and_save` | 246 | ✅ verified | run to `rts`, BOTH arms: nine offers over four tables, incl. the `>` boundary (a candidate EQUAL to the worst entry does not insert), an insert that walks slot 0 all the way to slot 4, the pending room staged with its high bit set, and a table staged UNSORTED. Plus a case that reads the sorted table back |
| `0x1207a` | `save_hiscores` **(+ a prologue slice** `[0x1207a, 0x120ce)` **)** | 292 | ✅ verified | run to `rts` over three tables, with a case that reads the forty ASCII bytes back out of the staged file against `../notes/frontend.md` §4. The PROLOGUE is a slice of its own over three entry counters, because the routine's FIRST mouse form is only observable there: `graf_mouse`'s whole image effect is `int_in[0]` and `addr_in`, and the closing call overwrites both before the `rts`. Composes `c_creat`, `c_write`, `c_close` and `itoa_padded` |
| `0x121a0` | `load_hiscores` | 386 | ✅ verified | run to `rts` over three shipped-shape files, a file with a non-digit mid-field (the parser has no length check — the byte test is what bounds it), 8 x 6 chunk-seeded random files, and a case reading the table back against `../notes/frontend.md` §4. Composes `c_open`/`c_read`/`c_close`/`c_lmul` |
| `0x13330` | `build_sprite_bank_grab_cells` **(the residual of `src/blit.c`'s slice,** `[0x13330, 0x1342e)` **)** | 254 | ✅ verified | the WHOLE of `build_sprite_bank` @ 0x132ec run to `rts` over the real `../bin/GHOST.DAT` — `src/blit.c`'s verified `build_sprite_bank_prepare` composed with this loop — so the case pins the composition as well as the sixty `c_malloc` + `vro_cpyfm` grabs and the 47/13 split between the two pointer tables |
| `0x1342e` | `save_sprite_backgrounds` | 200 | ✅ verified | four placements incl. one the VDI has to clip, 8 x 8 chunk-seeded fuzz, and poison. **Moved here from `src/blit.c`'s residual list** |
| `0x134f6` | `draw_sprites` | 220 | ✅ verified | as above; the OR mode is the transparency, and the fuzz draws every ghost tile and bubble frame |
| `0x135d2` | `restore_sprite_backgrounds` | 200 | ✅ verified | as above, plus a case that runs all three in order and asserts the work buffer comes back byte for byte — which is the protocol's whole point |
| `0x13a08` | `draw_room_to_stage` | 278 | ✅ verified | run to `rts` over four shipped rooms and the real GHOST.DAT, PLUS a per-cell slice `[0x13a20, 0x13afa)` run at all fifty cells with a mouse reading of its own at each. The per-cell slice is what makes the forty-nine interior polls observable at all — a poll over a fixed mouse state is idempotent, so a run to `rts` cannot tell fifty from one (measured: guarding the poll to the last cell passed the whole battery) — and it also compares the A2 the tile draw leaves against the oracle's, which is what closes the old residual. `src/blit.c`'s slice row for this address is retired as subsumed |
| `0x1396c` | `load_level_pictures` | 156 | ✅ verified | run to `rts` over the real `../bin/GHOST.DAT`: six 30,720-byte banks and the palette, six separate allocations in file order |
| `0x149b6` | `gem_aes` | 28 | ✅ verified | entered directly with the parameter block on the stack and `appl_exit`'s opcode staged — the one modeled AES call the game never makes, so the case reaches the trap without also being a test of a wrapper |
| `0x14b2e` | `aes_crysif` | 102 | ✅ verified | the four opcodes the model serves, D0 compared as the low word; the table's own bytes pinned against the loaded image; and two staged ROWS with a byte at or above 0x80, which is what shows the counts are widened SIGNED (see below) |
| `0x14b94` | `appl_init` | 84 | ✅ verified | from a ZEROED parameter block, so all seven longwords have to be written; `int_out` seeded with noise |
| `0x14be8` | `graf_handle` | 54 | ✅ verified | four SEPARATE out-pointers, which is not what its one caller does — it passes the same scratch word four times, so the four are told apart here and nowhere else |
| `0x14c1e` | `graf_mouse` | 30 | ✅ verified | M_OFF and M_ON. Its whole effect is OFF-IMAGE, so the ordered OS event ledger is the only thing that can tell a reconstruction which makes the call from one which does not |
| `0x16890` | `vdi_set_src_mfdb` | 34 | ✅ verified | five pointers incl. 0x80000000 and 0xfffefffe — the original splits with `asr.l`, so only a pointer with the top bit set shows that the sign fill is dropped by the `move.w` |
| `0x168b2` | `vdi_set_dst_mfdb` | 34 | ✅ verified | as above, over `contrl[9..10]` |
| `0x168d4` | `vdi_call` | 40 | ✅ verified | entered directly with an opcode staged: it parks A1/A2, re-points `contrl` and dispatches |
| `0x168fc` | `vst_height` | 76 | ✅ verified | five heights incl. 0, -1 and 0x7fff; four separate out-pointers over seeded noise |
| `0x16948` | `vst_color` | 44 | ✅ verified | nine pens incl. both ends of the model's 0..15 clamp and a negative one; D0 compared as the low word |
| `0x16974` | `vsf_color` | 44 | ✅ verified | as above |
| `0x169a0` | `v_opnvwk` | 102 | ✅ verified | from the loaded image's ZEROED parameter block, so all four lent pointers have to appear and be put back; two different `work_in` arrays (the attributes come out of that array, so a swapped slot installs a different pen); `work_out` seeded with noise so the 42 entries the model zeroes are visible; the handle passed IN is the BSS zero its real caller passes. Plus a case reading the workstation the model declares |
| `0x16a06` | `v_clrwk` | 32 | ✅ verified | over a screen full of noise, with poison |
| `0x16a26` | `vq_mouse` | 56 | ✅ verified | four poked states incl. both extremes, three separate out-pointers |
| `0x16a5e` | `vq_key_s` | 40 | ✅ verified | six shift masks |
| `0x16a86` | `v_gtext` | 92 | ✅ verified | seven strings x four positions — the empty string, a high-bit one, and the game's own longest menu line — at the origin, the far corner and a negative x the model clips; 8 x 8 chunk-seeded random strings; poison |
| `0x16ae2` | `vr_recfl` | 48 | ✅ verified | three rectangles (the bonus bar's own row among them) x three (interior, pen) pairs, the hollow one included: the model reads the fill INTERIOR before the fill colour, and a solid-only case could not tell the two reads apart |
| `0x16b12` | `vro_cpyfm` | 76 | ✅ verified | four rectangles x two modes x three raster directions, plus 8 x 12 chunk-seeded fuzz over ALL SIXTEEN logic operations and random extents; poison |

**276 cases.** The fuzzes are CHUNK-SEEDED rather than chunk-partitioned (`test/abi.py`'s `shard`
docstring tells the two apart), so each is `CHUNKS` x its own per-chunk count: `vro_cpyfm` 8 x 12
copies, `v_gtext` 8 x 8 strings, the sprite protocol 8 x 8 placements through each of three
routines, and `load_hiscores` 8 x 6 files. `make guarded` passes over the whole suite: this
subsystem indexes the image with addresses out of the parameter block and with the conterm pointer
it builds from a word, so that is its surface.

**Mutations tried against this battery.** Thirty-three, each from a deleted `build/` with
`__pycache__` swept and each measured against a **fully green whole-suite baseline** (the README's
step 6: a suite with one unrelated failing test reports every mutant as killed). Thirty are **red**;
the three that survive are proved EQUIVALENT below rather than left as holes.

**The last four rows were re-run on 2026-09-06** against a whole-suite baseline of 1595 passing, and
each is new: three name coverage this battery did not have until that day, and the fourth replaces a
mutation that used to be caught only by the attribution pass's refusal.

| mutation | what caught it |
|---|---|
| `contrl`'s ptsin and intin counts swapped | 140 cases — the sprite fuzz, and every `vro_cpyfm` case behind it |
| `v_gtext` reporting the terminator as a character | 52 cases — a `contrl[3]` one long is a different call |
| an MFDB pointer's two halves swapped in `contrl` | 63 cases |
| `v_opnvwk` never restoring the lent `ptsin` pointer | 3 cases — the next call reads the caller's array as ptsin |
| `vro_cpyfm` never restoring it either | the `vro_cpyfm` fuzz |
| `aes_crysif` widening the count table UNSIGNED | 2 cases — the staged rows below; nothing else in the battery could |
| the bubble sprite table reached with the UNBIASED base | `test_build_sprite_bank` |
| `draw_sprites` filling the pxy in the save direction | 12 cases |
| the A1 `c_read` leaves not tracked | 15 cases — every trap after a read files `c_errno`, not the caller's A1 |
| the A1 `c_write` leaves not tracked | 12 cases — the same fact on the writing side |
| `screen_back` computed ABOVE `Logbase` | `test_init_gem_and_screens` |
| the sprite cell's far corner one pixel short | 24 cases |
| the bank screen 12 cells wide instead of 10 | `test_constants.py`, by name |
| the tile draw's leftover A2 without the staging offset | the four `draw_room_to_stage` cases |
| the per-cell poll filing the CURRENT cell's leftover A2 | the same four |
| the hall-of-fame candidate compare widened to `>=` | the equal-score row |
| `draw_hall_of_fame` not clearing `room_number` to the backdrop room | 3 cases — and only since the case stages a DIFFERENT room on entry |
| the hall of fame drawn from its WORST entry down | 3 cases |
| the hall of fame's row pitch one pixel wide | 3 cases |
| one of the five hall-of-fame label rows moved a pixel | 3 cases — the labels are five separate `sub.w #imm` in the original and are transcribed as five values, so the row-pitch mutation above does not cover them |
| the two players submitted in the other order | 2 cases |
| the pending room widened UNSIGNED | 2 cases — the staged high-bit rows below |
| `save_hiscores` writing the room field six digits wide | 12 cases |
| `save_hiscores` showing the mouse where it hides it | 12 cases — the AES mouse mode is OFF-IMAGE, so the ordered OS event ledger is what sees this |
| `save_hiscores`' ENTRY mouse form taken as a constant | 2 cases — the prologue slice, which exists for this |
| the prologue's `Setscreen` skipped | 3 cases — the trampoline's three save slots |
| the per-cell `vq_mouse` guarded to the LAST cell (2026-09-06) | 49 cases — every `test_draw_room_to_stage_cell` but cell 49. It passed all 225 cases of this battery before the per-cell slice existed: a poll over a fixed mouse state is idempotent, so a run to `rts` sees only the last one |
| the tile draw reporting its A2 WITHOUT the tile band (2026-09-06) | 54 cases — the fifty per-cell slices compare the answer against the oracle's own A2, and the four whole-routine cases see the wrong register filed |
| the sprite trio's `src fd_addr := 0` deleted (2026-09-06) | 14 cases, by BYTE DIFF. With both MFDBs staged `fd_addr = 0` it was caught by ONE case and only as the attribution pass refusing the run; the two MFDBs now enter holding distinctive junk rasters, so a deleted store makes the copy read the wrong raster |
| the grab of sprite cell 50 skipped (2026-09-06) | `test_build_sprite_bank`. It passed all 225 cases before the Malloc arena was seeded: cell 50 (`bubble_sprite[3]`) is 512 ZERO bytes in the real GHOST.DAT, and an untouched `c_malloc` buffer is zero too |

**Three mutations SURVIVE and are EQUIVALENT, not holes.** Each is recorded with its proof so nobody
re-tries it. A FOURTH used to be listed here and has moved to the residuals below —
`save_hiscores`' exit mouse form, whose equivalence holds only under a model gap, which makes it a
premise rather than a proof:

1. **The bubble sort's FIFTH pass.** Four passes instead of five is byte-identical for every input,
   and provably: the table has five entries and each pass makes four ADJACENT compares, so after
   four passes the largest four elements have each reached their place — a fifth pass can never
   swap. The original makes it anyway (it counts its swaps in a local it never reads, so there is no
   early exit), and the reconstruction transcribes that.
2. **The A1 `save_hiscores` RETURNS with not escaping to its caller.** The transcription is right —
   its `c_write`s leave A1 at `c_errno`, and the two-player arm's second offer traps with no
   intervening call — but the evidence is overwritten: every later trap in the second pass re-files
   `c_errno`, so the final slot agrees whatever the reconstruction threaded. Closing it means a
   `stop_pc` inside the second pass, which is a slice of `hiscore_submit_players` nothing else wants.
3. **`save_hiscores` creating the file through `load_hiscores`' copy of the name.** The two are
   different addresses holding the same eleven bytes, and the model resolves a staged file by NAME,
   so no run can tell them apart. `test_the_loaders_open_the_names_the_reconstruction_points_at`
   pins each address's contents instead, and a case asserts the two addresses differ.

**Three mutations were survivors on the first pass, and each names a branch the GAME'S OWN DATA
CANNOT REACH.** They are why three groups of cases exist, and each stages the value rather than
inventing an answer:

* **`aes_crysif`'s SIGNED count bytes.** Every row the program asks for (opcodes 10, 19, 77, 78)
  holds 0, 1 or 5, and the first byte at or above 0x80 in the whole table belongs to opcode 126 —
  which the model does not serve, so the run would be REFUSED rather than compared. The case stages
  the row instead: the table is ordinary image memory both sides read, so a row with a high byte in
  it is an input to the routine's arithmetic and not a fabricated answer.
* **the pending room's SIGNED widening.** A room is 0..35 and even a corrupt GHOST.SCR parses at
  most 99, so the `ext.l` is unreachable through the game's data. The word is staged with its high
  bit set — it is a plain word global and the case pokes it, like any other input.
* **the per-cell poll's A2 ordering**, which needed the tracking to move with the statement before
  it was a real mutation at all.

**One mutation is EQUIVALENT for a different reason**, and is recorded so nobody re-tries it either:
swapping the `vq_mouse` and the tile draw inside `draw_room_to_stage`'s loop WITHOUT moving the A2
tracking with them. The two write disjoint regions — the input block and the staging area — and the
register the poll files is unchanged, so no image can tell the orders apart. Moving the tracking too
is the real mutation, and it is red. So is `init_gem_and_screens`' `work_in` loop bound: raising it
from 10 to 11 writes a 1 into `work_in[10]` that the very next line overwrites with 2.

### Residuals — what these rows do NOT pin

1. **`save_hiscores`' EXIT mouse form is equivalent UNDER THE MODEL, and the premise is the model
   gap.** The reconstruction files the routine's own loop counter, and after the loop that counter
   IS `HISCORE_SLOTS`; a version that passed the constant is byte-identical for every case. The only
   path on which the two differ skips the loop, and it is the `c_creat` FAILURE arm — which no run
   can reach, because `os_fcreate` REFUSES an unstaged name rather than answering negative
   (residual 7 below is the same premise on the reading side). So this is not a proved equivalence
   about the program: it is an equivalence about the program *as the model can run it*, and it stops
   being one the day the model can answer a failed create. Recorded here, beside the other things
   the rows do not pin, rather than in the mutation table's list of equivalents.
2. **The A1 `save_hiscores` returns with is threaded but not PINNED**, and the mutation table's
   third equivalent says why: every later trap re-files `c_errno`, so the value the two-player arm
   carries into its second offer is overwritten before the `rts`. It is transcribed rather than
   dropped because it is what the machine does; closing it means a `stop_pc` inside that second
   pass, which is a slice of `hiscore_submit_players` nothing else wants.
3. **Every XBIOS call this subsystem makes is a NO-OP in the model.** `Getrez`, `Logbase` and
   `Setpalette` write hardware or answer a machine fact, so what a reconstruction reproduces is the
   trampoline's three save slots and the modeled result — a wrong palette or a wrong screen base is
   byte-identical here. **The surface is the on-target smoke run** (`docs/on-target-execution.md`),
   and this project has no `.PRG` yet.
4. **The VDI's colour indices are the model's, not TOS's.** The model writes the colour index
   straight into the planes; real TOS maps VDI pen numbers through a table, so a reconstruction
   verified here draws the right shapes in the wrong colours on a real machine (TRAP_MODEL.md,
   Phase 12). Same class as 3, and the same surface.
5. **The font is the model's synthetic glyph set, not TOS's.** Every `v_gtext` case compares the
   pixels both sides draw from one parameter block, which is the whole of what a differential can
   pin; whether those pixels read as text is an on-target matter.
6. **`graf_mouse`'s `mform` argument is stack garbage at both call sites**, which push only the mode
   word — so the long it reads is really the caller's own return address. It is an argument here for
   that reason, and the AES ignores it for M_OFF and M_ON; the claim is about the AES, not something
   a case observes.
7. **The failure arm of all four loaders is unreachable under the model.** `os_fopen` REFUSES an
   unstaged name rather than answering negative, so the retry loop runs once and
   `load_hiscores`' "no file: every score 0, every room 1" path is transcribed and read-verified.
8. **The `short` return values are compared as D0's LOW WORD**, which is the Alcyon C ABI's answer
   and what every caller reads. `vst_color`, `vsf_color`, `aes_crysif`, `appl_init` and
   `graf_handle` are the routines here that answer at all.
9. **CLOSED, and recorded so the shape is not re-invented.** Three 68000 idioms used to have a
   second home in `src/frontend.c`: `LONGWORD_BYTES` (a second NAME for `src/blit.c`'s `LONG_BYTES`,
   which `test_constants.py`'s name-keyed duplicate check could never see), `tile_draw_leaves_a2`
   (a second spelling of the `muls.w`+`ext.l` destination arithmetic) and `show_presentation`'s
   30,720-byte copy loop (a second spelling of `copy_longs_ascending`). They now live in
   `include/common.h` — `LONG_BYTES`, `muls_ext_w`, `copy_longs_ascending` and `longword_slot` — and
   the A2 restatement is gone entirely: `draw_room_tile_to_stage` REPORTS the register it leaves.
   `include/common.h`'s own header says why these are not in the kit's `machine.h`: that header is
   the ISA, and these are the Alcyon compiler's idioms.
10. **`vro_cpyfm`'s MFDB record is named twice, once per side of the seam**, and the two sets are
   pinned equal TO EACH OTHER by a single `_Static_assert` in `src/frontend.c` rather than by a
   redefinition warning: only two of the six fields are spelt the same in both headers
   (`include/blit.h`'s `MFDB_WIDTH`/`HEIGHT`/`STANDARD`/`PLANES` against the kit's
   `MFDB_W`/`H`/`STAND`/`NPLANES`), so a drift in the other four could never warn at all. The game's
   six values are captured under private `GAME_MFDB_*` names, all six of the game's spellings are
   `#undef`ed — not just the two that collide, so a line in that file meaning the model's record
   cannot silently be written against the game's — and the assertion compares one header with the
   other. It used to be two assertions against LITERALS, which would both have had to be edited to
   move a field. That file is the only translation unit that includes both.

11. **A NEGATIVE `c_read` is unreachable, so the arm that skips the A1 report is transcribed and not
   run.** `src/frontend.c`'s loaders call `c_read_reporting` / `c_write_reporting`, which record A1
   at `A_c_errno` exactly where `c_getfdmode` leaves it — and `c_read` exits at 0x16710 BEFORE that,
   with A1 untouched, when the first Fread comes back negative. No case can produce one: the model
   refuses an unstaged file rather than answering an error, and a staged file always reads. The
   difference is why this file no longer wraps `c_read`/`c_write` and assigns A1 unconditionally
   afterwards, but the arm itself is read-verified. Its console twin is a premise instead of a
   residual: `test_no_loader_opens_a_console_pseudo_handle` asserts that none of the five names this
   subsystem opens is "CON:", "AUX:" or "PRT:", which is what makes a pseudo-handle unreachable.


## Verified — gameplay (10)

The in-room simulation: the castle's four data tables, the ghost, the blow, the bubble and the
hazard model — plus the HUD's number formatter. `../notes/gameplay.md` is the design doc,
`include/gameplay.h` the frozen record layout, and `src/gameplay.c`'s header comment says why
`game_frame_update` is seven slices rather than one function.

**This subsystem now owns the three globals `include/blit.h` held on loan.** `A_room_number`,
`A_object_table` and `A_room_table` — and the `OBJECT_*` / `ROOM_*` record offsets that moved with
them — are defined in `include/gameplay.h`; `src/blit.c` includes it to read them, and the three
rows that predicted this move are gone from "Borrowed globals" below.

**The two regions of `game_frame_update` that are NOT here, and neither limit is this
subsystem's.** Its front-end poll (`vq_mouse` @ 0x16a26, `vq_key_s` @ 0x16a5e and the `Crawio` key
read, 0x1233a..0x12434) is the front end's own VDI/console binding, unported — a slice boundary
either side of it is what keeps this file from carrying a second copy of somebody else's routine.
Its death sequence (0x1273c..0x1294a) calls `save_sprite_backgrounds` / `draw_sprites` /
`restore_sprite_backgrounds`, which are `src/blit.c`'s and unported. Both are in "Not
reconstructed" with what would close them.

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10f20` | `reset_world_state` | 936 | ✅ verified | run to `rts`; 3 seeds of noise over the three room-indexed tables and both players' 58-word blocks, plus poison. 174 straight-line stores, one list |
| `0x114ee` | `itoa_padded` | 232 | ✅ verified | run to `rts`; every digit count the HUD reaches (0..0x7fffffff) x widths 1 and 6, widths 0/2/8, the three NEGATIVE values (`c_ldiv` is signed, so those write characters below `'0'`), and poison. Composes the verified `c_ldiv` and `c_strlen` |
| `0x129b4` | `ghost_blow` **(slice** `[0x129b4, 0x12ff8)` **)** | 1604 of 1616 | ✅ verified | `stop_pc` at the `jsr hud_draw_counters` that ends the candle script — the score award IS inside the slice, only the drawing of it is not. Covers: the puff and its idle-voice gate; the `|dx| < 50` / `|dy| < 50` range gate at both bounds and at -32768 (`neg.w` of the most negative word is itself); all eight facings armed and all eight missed; the four diagonal cones at their `bge`/`ble` boundaries; the candle script over all ten shipped candle rooms, each placed from the room's OWN data; the four window bounds from both sides; the left-facing requirement. **Residual:** `hud_draw_counters` @ 0x113d2 and `present_score_strip` @ 0x131f0 |
| `0x12322` | `game_frame_update` **(7 slices)** | 902 of 1682 | ✅ verified | Seven mid-entry slices, each entered at its own PC and diffed at the next one's: `[0x12322, 0x1233a)` the bubble's frame counter; `[0x12434, 0x124a4)` the mouse divided down through the software float package; `[0x124a4, 0x1255c)` blowing or recovering (entered with the caller's A1/A2, which the two `Setcolor` trampolines file); `[0x1255c, 0x125e6)` the mouse buttons' facing latches; `[0x125e6, 0x126e2)` the two fan slots; `[0x126e2, 0x1294a)` the bubble's own step, pop included; `[0x1294a, 0x129b0)` the drift pulse. **Residuals:** the front-end poll `[0x1233a, 0x12434)` and the death sequence `[0x1273c, 0x1294a)` — see above — and slice 3's ONE precondition below |
| `0x13004` | `bubble_collision_probe` | 492 | ✅ verified | run to `rts`; the phase stepped from 0..5 and from outside it, each of the eight rim probes driven alone with one non-background pixel under it, the word-truncated phase offset at phase 1024, and 8 x 12 chunk-seeded fuzz cases over a noisy screen. Composes `get_pixel` |
| `0x13bea` | `get_pixel` | 130 | ✅ verified | run to `rts`, ANSWER compared (it writes nothing): all sixteen colour indices, all sixteen bit positions, five rows of ladder addressing, six negative-x rows (`divs.w` truncates toward zero and the bit index runs past 15), four row-offset wrap rows, and 8 x 12 chunk-seeded fuzz |
| `0x13d2c` | `restore_world_p1` | 356 | ✅ verified | run to `rts`; 3 noise seeds + poison, and the numbered-block case that pins the block being filled BACKWARDS |
| `0x13e90` | `restore_world_p2` | 356 | ✅ verified | as above |
| `0x13ff4` | `save_world_p1` | 356 | ✅ verified | as above |
| `0x14158` | `save_world_p2` | 356 | ✅ verified | as above |

**396 cases.** The fuzzes are CHUNK-SEEDED rather than chunk-partitioned (`test/abi.py`'s `shard`
docstring tells the two apart), so each is `CHUNKS` x its own per-chunk count: `get_pixel` 8 x 12
probes, `bubble_collision_probe` 8 x 12 worlds, the fan test 8 x 10 placements and the bubble step
8 x 8 velocity/screen pairs. `make guarded` passes: `get_pixel` indexes the image with an address
it computed from a signed row offset and a signed cell index, with no bounds test of any kind.

**No poison pass on the collision probe or on the frame slices**, and the reason is
`docs/agent-playbook.md` §8's: `probe_phase`, `bubble_frame`, `breath`, `ghost_anim` and
`drift_pulse` are all read-modify-write counters that also STEER the run, so pre-inverting them
diverts it instead of catching a coincidence. The routines that only write — the world block's
five, `itoa_padded` — are run under poison.

**FOUR staging decisions, each of which a measured survivor forced.** They are the same defect four
times — a case that stages the value the routine is about to write, so writing it and not writing it
look alike — and they are written here because the next case added to this battery will want them:

* **`drift_vel_x` / `drift_vel_y` are seeded NON-ZERO** in every blow case. An orthogonal blow arms
  only the axis it moves along; against a zero that is indistinguishable from a reconstruction that
  wrote `0 * speed` to the other. Measured: the both-axes form passed all 360 cases.
* **`drift_pulse` / `drift_interval` too**, for the same reason one field over: `arm_drift` clears
  both, and a reconstruction that dropped the two clears passed all 374.
* **A "busy" voice stages BOTH `SND_VC_DURATION` and `SND_VC_PRIORITY`, and the priority is BELOW
  the puff's own.** `sound_voice_priority` reads the priority and `sound_release_voice` returns at
  once on a zero duration — and with a priority ABOVE the trigger's, `sound_play` refuses by itself,
  so a reconstruction with no idle-voice gate at all is still byte-identical. Both halves were
  measured as survivors.
* **`ghost_x` / `ghost_y` are seeded non-zero in the mouse-scaling cases**, or the `mouse = (0, 0)`
  rows pass with the whole slice deleted.

**Mutations tried against this battery**, each from a deleted `.so` with `__pycache__` swept, and
each **red**:

| mutation | what caught it |
|---|---|
| `get_pixel` counting bits from the RIGHT of the plane word | 38 cases — the bit-position ladder and every probe case behind it |
| `get_pixel`'s row offset multiplied in 32 bits (no `ext.l`) | 4 cases — `test_get_pixel_row_offset_wraps_in_a_signed_word`, which is the only thing that reaches row 205 |
| the probe using the phase it ARRIVED with instead of the stepped one | 8 cases |
| the probe's phase offset added in 32 bits | 1 case — `test_probe_phase_offset_wraps_in_a_signed_word`, built for it: the game's own phase never leaves 0..5, so the case plants eight probe pairs at the word-truncated address itself |
| `arm_drift` writing BOTH velocities on an orthogonal blow | 11 cases — and only after the staging decision above; it survived on zeroed velocities |
| the candle's two map-patch tiles swapped | 10 cases |
| the world block filled forwards | 21 cases — including `test_world_block_is_filled_backwards`, which numbers all 58 words |
| the drift pulse firing after the decrement rather than on the frame it was already 0 | 25 cases |
| the fan's room offset added in 32 bits (`add.l` instead of `adda.w`) | 2 cases — `test_frame_apply_fans_room_offset_wraps_in_a_signed_word`, which plants a fan where the WORD-truncated offset points; the game's own 0..35 never overflows |
| `ghost_blow`'s object room offset truncated to a word (the fan test's shape) | 2 cases — the mirror-image case, which plants the flame object where the 32-BIT address points |
| `itoa_padded` padding one short | 12 cases |
| the blow range gate widened from `< 50` to `<= 50` | 1 case |
| the blow range gate measured in 32 bits (a total `abs`) | 2 cases — the -32768 rows, each facing the direction that offset would blow in |
| `blow_facing_plus1` computed without the `+ 1` | 87 cases |
| the bubble frame wrapping at 11 instead of past 12 | 1 case |
| the bubble step dropping the fan's `x_impulse` | 10 cases |
| the two `Setcolor` return addresses swapped | 2 cases — the trampoline's three save slots are the whole of what a reconstruction can reproduce about a modeled-as-no-op trap |
| room 35 scaled with the ordinary mouse divisor | 3 cases |
| `DRIFT_SPEED_FLOOR` 100 -> 150 | 5 cases |
| `DRIFT_INTERVAL_MAX` 200 -> 100 | 3 cases |
| the facing wrapping one step early (`>= 7` / `<= 0`) | 2 cases — and only after `test_frame_step_facing_wraps` grew the rows JUST INSIDE each end |
| the left button's latch never re-arming | 18 cases |
| the puff's idle-voice gate deleted (`if (1)`) | 13 cases — and only after a busy voice stopped being staged at field 0 with a priority above the trigger's |
| either `sound_release_voice` in slice 3 replaced by a no-op | 2 and 10 cases — the `voice_busy` rows of the shift-gate and breath batteries |
| the cone test deleted from the up-right arm / from the up-left arm | 2 cases each — and only after `test_ghost_blow_cone_boundaries` grew rows that reach ±40 on all four cones, not just two |
| `arm_drift` dropping `drift_interval := 0` / `drift_pulse := 0` | 31 cases |
| `frame_scale_mouse_to_ghost` emptied | 18 cases — all of them, where 15 of 18 before |
| slice 6 always answering "the death sequence" | 5 cases — the dead-bubble rows, which now check the flag |
| the candle's x window widened at both ends (`>` / `<`) | 2 cases |
| the fan's dy band widened at both ends | 4 cases |
| `extinguish_candle` reading `A_room_number` ONCE instead of re-reading it | 1 case — `test_ghost_blow_candle_patch_can_move_the_room_number`, the only thing that separates the two programs |
| the candle's two DEST slots swapped (2026-09-06) | 13 cases — the extinguish script writes each record's tile into the other's slot |
| `muls_ext_w` multiplying in 32 bits, now that it lives in `include/common.h` (2026-09-06) | 11 cases across TWO batteries — `test_gameplay.py`'s two `get_pixel` row-offset wraps and its fuzz, and `test_blit.py`'s two tile-offset wraps and the wipe's word-sized counter. The helper used to be a private copy in each file, so a mutation had to be made twice to be measured once |
| a frame slice's `stop_pc` moved two bytes (2026-09-06) | 40 cases, and `test_constants.py::test_entry_addresses_still_point_at_their_routines` BY NAME — the `STOP_PROLOGUES` pin, which did not exist before that day |

**Twelve of those were survivors** — six found by the port agent's own sweep and six more by an
independent reviewer — and each is why a case or a staging decision exists at all: the zeroed drift
velocities and pulse schedule, the two room-offset wraps, the probe's phase-offset wrap, the facing
wrap's inner rows, the range gate's -32768 rows facing the wrong way, the busy voice staged at the
wrong field, the two `sound_release_voice` calls nothing reached, the two untested cones, and the
zeroed ghost position under a zero mouse.

**One of the review's findings was a REAL DEFECT, not a coverage hole**, and it is the reason
`extinguish_candle` reads `A_room_number` twenty-eight times where a reconstruction naturally reads
it once: the first map patch can store into `A_room_number` itself (a tile column of 2923 puts
`room_table[0].map[0][x]` at exactly 0x23120), and everything after that store then works on the
room the store left. The first version of this port cached it, and no case reached the difference
until one was built for it.

**A FOURTH SURVIVOR, measured 2026-09-06 and equivalent by proof:** `set_object_tile_for` caching
`A_room_number` WITHIN one call instead of reading it twice. The original reads the word once to
reach the candle record and again to reach the object table, and the reconstruction transcribes
that — but nothing between the two reads writes memory, so the two are one for every input. What is
NOT equivalent is caching it ACROSS the four calls, which the row above shows is red: a store made
by one call can land on `A_room_number` itself.

**Three mutations were tried and are EQUIVALENT, not holes**, and are recorded so nobody re-tries
them: `itoa_padded` reversing on its own digit count instead of re-measuring with `c_strlen` (the
digits it writes are `'0' + r` for `r` in -9..9, never a NUL, so the two lengths agree for every
reachable input); `speed < DRIFT_SPEED_FLOOR` widened to `<=`; and `breath > BREATH_MAX` widened to
`>=` — the last two write the same value they were about to clamp to. A mutation the suite does not
catch is a coverage hole, not a licence — record it here.

### Residuals — what these rows do NOT pin

1. **The composition of the seven frame slices.** Each is diffed over its own region, and the ORDER
   they run in is read-verified rather than run: no case enters `game_frame_update` at 0x12322 and
   leaves at 0x129b0, because the front-end poll between them is unported. Closing it is the front
   end's `vq_mouse` / `vq_key_s` / `Crawio` path, after which the whole routine runs to `rts`.
2. **The two `Setcolor` calls are no-ops in the model.** XBIOS `Setcolor` writes the shifter, which
   is not image state, so a reconstruction that recoloured the ghost wrongly — or never at all — is
   byte-identical here. Only the trampoline's three save slots are compared. **The surface is the
   on-target smoke run** (`docs/on-target-execution.md`), and this project has no `.PRG` yet.
3. **`frame_blow_or_recover` takes the caller's A1/A2 as an argument** (`docs/agent-playbook.md` §5,
   "a parameter"). The two trampolines file whatever the register file holds and nothing in the
   slice computes it; the case hands the same values to both sides. Nothing between the entry and
   either trap writes an address register (`sound_voice_priority` @ 0x1455e and
   `sound_release_voice` @ 0x14510 touch only D0/A0), so the claim is read-verified from two short
   routines rather than assumed. Closing it means porting `game_top_loop`.
4. **`frame_step_live_bubble` answers a flag this reconstruction invented.** The original falls
   into the death sequence; the core returns non-zero instead, because a silent fall-through in a
   function whose composition matters is a correctness trap. Every case asserts it is 0 — the run
   reached the stop PC, so it did not enter the sequence — which is a self-consistency check and
   not a comparison with the oracle. **`BUBBLE_DEATH_TRIGGER_FRAME` (3) is therefore unpinned on
   the other side**: no case can stage a dead bubble past frame 3, because the oracle would enter
   the unported sequence and never reach the stop. Porting the three sprite routines closes it.
5. **The `short` return values are compared as D0's LOW WORD**, which is the Alcyon C ABI's answer
   and what every caller reads. `get_pixel` is the only routine here that answers at all.
6. **Slice 3 calls `ghost_blow_body`, which is `ghost_blow` MINUS its two redraws** — and the
   original reaches those only when the candle script fires, every other exit branching over them.
   So the slice is equivalent to the original exactly while the current room has no candle left,
   which is what every slice-3 case stages (`candle_table[room][0] = -1`). Closing it is the same
   `hud_draw_counters` the `ghost_blow` row is waiting on.

## Verified — blit (10)

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
| `0x13b1e` | `room_wipe_in` **(slice** `[0x13b62, 0x13bda)` **)** | 120 of 204 | ✅ verified | each of the 40 steps entered on its own with `D7 = step`, plus the whole loop twice — over noise, and over a staging area the ORACLE composed with 50 real tile draws first. Plus the two steps the game's own loop never reaches, which are what pin the present's WORD-sized `dbf` counter against the `mulu`'s longword product: step 409 (64 longs presented, not 65,600) and step -1 (the full 65,536, on a low staging of its own). **Residual:** the three `sound_release_voice` calls and the `sound_play` around it |

**Not here, and it is an OWNERSHIP boundary rather than a model gap.** `save_sprite_backgrounds` @
0x1342e, `draw_sprites` @ 0x134f6 and `restore_sprite_backgrounds` @ 0x135d2 are three `vro_cpyfm`
pairs each — they were a refused oracle run until TRAP_MODEL.md Phase 12 modeled VDI opcode 109 over
Phase 11's raster, and they are now **verified in `## Verified — frontend`**, with the sprite
protocol and the binding that carries it rather than with the raw `move.l` blitters.

**`draw_room_to_stage` @ 0x13a08 HAD A ROW HERE AND NO LONGER DOES.** Its slice `[0x13a38, 0x13afa)`
— one iteration of the 5 x 10 loop — is SUBSUMED by the whole-routine row in `## Verified —
frontend`, which composes this file's `draw_room_tile_to_stage` with the per-cell `vq_mouse` and runs
the routine to `rts`. One address, one ✅ row: `test/test_status.py` refuses a second, because two
rows for one routine make the ledger's counts say more work was done than was. The tile draw's own
cases (`test_blit.py`'s 50 cells, 36 rooms, 80 fuzz, poison and the two `ext.l` wraps) are unchanged
and are what the frontend row rests on.

**`build_sprite_bank`'s slice DOES still have a row**, and the difference is worth reading: its
residual `[0x13330, 0x1342e)` is filed under an address of its own
(`build_sprite_bank_grab_cells`), so the two rows name two disjoint spans rather than one routine
twice. `room_wipe_in`'s residual is the sound engine's and stands.

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

## Verified — clib (53)

The Alcyon/DRI C runtime linked into the program, `src/clib.c` / `include/clib.h` / `test/test_clib.py`.
Ported in dependency order: the string and 32-bit arithmetic leaves, the fd-mode side table, the
free-list allocator, the low-level file layer, the whole software floating-point package, the
buffered `FILE` layer on top of it, the console reader and writer, and the printf engine — and with
them the two OS trap trampolines, which are verified through the wrappers that call them.

**The whole C library is now ported bar five wrappers**, each of which needs one GEMDOS call the kit
does not model; they are the only rows left in "Not ported" below.

**FOUR SHAPES OF EVIDENCE**, because most of this subsystem answers somewhere the byte diff cannot
see. A routine whose answer is D0 is checked against the oracle's D0 as well as by the image diff.
`c_ldiv` and `c_lmul` answer through their CALLER'S argument slots, which lie in the band the
differential drops as stack — those run from a poked stub (`test/abi.py`'s `c_call_pokes`) that
files the answers at `abi.RESULT`. And the trap trampolines' only reproducible effect is the three
save slots, so every case that traps stages noise over them: the `RET_*` value a wrapper leaves says
WHICH trap site ran, which is what tells a binary `c_read` (one Fread) from a text one (several).

**A FOURTH SHAPE OF EVIDENCE ARRIVED WITH THE CONSOLE: the kit's ordered OS-event ledger**
(TRAP_MODEL.md, Phase 13). `c_conout_write`, `c_write`'s CON: arm, `c_conin`'s echoes and everything
`c_printf` puts on the screen move no image memory at all — a reconstruction that printed nothing
would be byte-identical to one that got them right. `harness.differential` compares that ledger on
every run without a case asking for it, which is what makes those five routines verifiable rather
than merely read.

**The floating-point package is byte-compared, never float-compared.** It keeps a 32-bit mantissa
where an IEEE double has 53, so "the same number in Python" and "the same eight bytes" are different
questions and only the second is asked. Half the fuzz's operands are raw 64-bit patterns rather than
doubles Python would name — the package has no special case for an infinity, a NaN or a denormal (a
zero EXPONENT is the only value it tests for), so those are ordinary inputs to it.

**568 cases.** The fuzzes are CHUNK-SEEDED rather than chunk-partitioned (`test/abi.py`'s `shard`
docstring tells the two apart), so each is `CHUNKS` x its own per-chunk count: the ldiv/lmul fuzz is
8 x 24 pairs through each routine, the allocator fuzz 8 x 16 arenas, the arithmetic fuzz 8 x 24
operand pairs, the conversion fuzz 8 x 24 patterns through each of three routines, and the printf
fuzz 8 x 24 random formats. `make guarded` sweeps the same suite clean — the allocator and the
buffered layer both index the image with cursors they compute, so that is their surface.

**FOUR OF THE 567 ARE CANDIDATE-ONLY, and they are the file's out-of-bounds guards.** The original
overruns its own frame in three places — `c_fmt_integer`'s 20-word digit array for a base below 8,
`c_fcvt`'s digit buffer for a count `c_fmt_float` derives from a format string's precision, and the
same buffer for a NEGATIVE count (`c_fmt_getnum` accumulates in 16 bits and wraps, so `%.65534f`
arrives as -2). There is nothing comparable to diff against: the oracle would smash its stack and
the candidate would write outside a C array, which in the harness's own process is an xdist worker
vanishing rather than a red case. So the reconstruction REFUSES each, and those four cases drive the
glue directly and assert the refusal tally (`g_os_refusal_count`) instead of an image.

**WHAT THE PRINTF ENGINE IMPLEMENTS**, read off `c_doprnt`'s own dispatch chain and fuzzed over that
and no more: `%[-][0][width][.precision][l]` then one of **d u o x c s e f g**. There is no `%%` (a
second `%` reaches the "unknown conversion" arm and is emitted as itself, which is the same output by
a different route), no `+`/space flag, no `*` width, no `h`, and no `p`/`n`/`i`; `%g` is `%e`, since
`c_fmt_float` tests for `'f'` and takes the exponent form for everything else. **The game itself uses
none of them**: its one `c_printf` call (`main` @ 0x100dc) passes the "Please reboot in LOW REZ"
message, which carries no conversions at all — so every other format in the battery is synthetic, and
that is a statement about coverage rather than about play.

**`Malloc` IS THE KIT'S MODEL ON BOTH SIDES.** `gemdos_malloc` / `gemdos_malloc_or_fail` forward to
`os_malloc` (`tools/recreate_kit/src/os_heap.c`) — the same bump arena, over the same
`heap_base`/`heap_limit` window, that `oracle/shim.c` services the GEMDOS trap from. So the two bump
pointers are comparable after every run (`harness._vet_heap_pointers_agree`), which is what catches an
allocation the reconstruction never makes: the first block of an untouched arena IS the base, so a
wrapper that answered `OS_HEAP_BASE` without allocating would store the byte-identical longword. The
`Malloc(-1)` query — GEMDOS's "how big is the largest free block?", which answers a SIZE and moves
nothing — is the model's too and is now a case (`test_gemdos_malloc[0xffffffff]`). This battery used
to carry a private copy of the arena's two lines in `src/clib.c`, reset per run from `test/abi.py`;
both are gone, and `harness.arm_candidate` rewinds the kit's pointer instead.

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

**A third sweep, re-run when the allocator moved onto `os_malloc`** — the same three questions the
private arena used to answer, asked of the model:

| mutation | result |
|---|---|
| `MALLOC_GRANULE` 6 → 8 | **red** (27 cases) — the granule is the header's own size, so every c_malloc/c_free/c_morecore case walks a differently-spaced list |
| `c_morecore`'s round-up loses its `- 1` (`+ QUANTUM` instead of `+ QUANTUM - 1`) | **red** (2 cases) — `test_c_morecore[1048]` and `[2096]`, the EXACT multiples of the 0x418-granule quantum, where an off-by-one round-up asks GEMDOS for a whole extra quantum |
| `gemdos_malloc` answers `Malloc(-1)` with the arena base instead of forwarding the query | **red** (1 case) — only since the query became a case; the oracle answers the free window (0x60000) and the wrapper answered an address |

**A fourth sweep, over the buffered layer, the console and the printf engine** — eighteen mutants,
each from a deleted `.so` with `__pycache__` swept, against a green `test_clib.py`:

| mutation | result |
|---|---|
| the FILE record's `bufsiz` offset 18 → 16 | **red** (22 cases) |
| `CRLF_BYTES` 2 → 1 (a newline goes out as one byte) | **red** (6) |
| `FILE_LINEBUF` moved from 0x100 to 0x200 | **red** (7) |
| `FMT_NO_PRECISION` moved from 0x100 to 0x200 | **red** (3) |
| `c_write` charges a newline two bytes instead of one | **red** (5) |
| `c_fcvt` rounds with 4 instead of 5 | **red** (8) |
| `c_filbuf` always asks for a whole buffer, never one byte | **red** (2) |
| `c_doprnt`'s right-justify off by one (`width` for `width - 1`) | **red** (13) |
| `c_fread` stops threading the A1 that `c_getfdmode` left behind | **red** (1) |
| `c_conout_write` stops prefixing a newline with a CR | **red** (4) |
| `c_fmt_float` sends `%g` down the `%f` path | **red** (17) |
| `c_putc` flushes one byte early (`<= 0` for `< 0`) | **red** (3) |
| `FMT_HEX_STEP_MASK` widened by a bit | **red** (6) — *see below* |
| `FMT_OCTAL_STEP_MASK` widened by a bit | **red** (8) |
| `unbuffered_char_slot` drops `divs.w`'s remainder | **red** (1) — *see below* |
| the sign-fill of `shift_right_arithmetic` replaced by zeros | **SURVIVES**, with a proof |
| `CLIB_SCRATCH_EXPONENT_ARGS` overlapped onto `CLIB_SCRATCH_FCVT_DOUBLE` | **SURVIVES**, with a proof |

**Two of them found real holes and closed them, which is the point of the sweep.**

* The **step masks** survived their first run, and the reason was the C rather than the battery: the
  octal and hex digit loops step the value with `asr.l`, and the mask that follows exists to clear
  the sign fill. Written with an unsigned `>>` the fill was never there, so the mask could be widened
  by a bit and nothing changed. `shift_right_arithmetic` spells the fill out — C's `>>` on a negative
  signed value is implementation-defined — and both masks are load-bearing now. What still cannot be
  caught is the PAIR: fill-then-mask and no-fill-then-no-mask compute the same function, so dropping
  the fill alone survives. The form that is there is the one that reads as the `asr.l` it transcribes.
* **`unbuffered_char_slot`'s remainder** survived until a case was written for it. `divs.w` leaves the
  remainder in D0's HIGH word and the `adda.l` that follows adds the whole longword, so a FILE record
  two bytes off the 20-byte stride puts its one-byte buffer 0x20000 further up the image. No caller
  in the program passes such a pointer, so `test_c_filbuf_off_stride_record_lands_the_divs_w_
  remainder_in_the_high_word` fabricates one — a legal argument to the routine, not a fabricated
  record — and the mutant now reddens.
* **The scratch overlap cannot be caught, and the reason is the residual above.** Both spans live in
  the band the differential drops, and in the one path that uses both — `%e` — `c_fcvt` has finished
  with its working double before the exponent argument list is written. So the overlap changes
  nothing a case could see, on either side.

**A fifth sweep, over what the pre-commit review changed** — the same protocol, run against
`test_clib.py` **and** `test_constants.py`, because three of these are header constants a battery
mirrors rather than exercises:

| mutation | result |
|---|---|
| `note_fd_modes_consulted` stops recording the A1 `c_getfdmode` leaves | **red** (31) |
| `c_fmt_integer`'s digit-array bound doubled | **red** (1) — the candidate-only guard case |
| `C_FCVT_DIGITS_OVERHEAD` 3 → 0 (the bytes c_fcvt writes past `ndigits`) | **red** (2) |
| `CLIB_SCRATCH_BASE` dropped below `STACK_TOP - STACK_SCRATCH` | **red** (1) |
| `c_fmt_float` stops refusing a NEGATIVE precision | **red** (1) |
| `c_fcvt` stops refusing a negative digit count | **red** (1) |
| `C_EXPONENT_ARGS_OFF_VALUE` 4 → 2 | **red** (30) |
| `file_take_through_cursor` stops advancing the cursor | **red** (11) |

Two of those started as survivors and named their own case, which is the sweep earning its keep: the
`c_fcvt` negative-count guard had no caller that could reach it (`c_fmt_float` refuses first), and
`c_fmt_integer`'s bound had none either. Both are candidate-only cases now. A third — the header
constants — survived only until the sweep was widened to run `test_constants.py` beside the battery;
a mirror is a real pin and a sweep that omits the file holding it reports a phantom survivor.

**THE SCRATCH MOVED because of the review, and the pin moved with it.** `CLIB_SCRATCH_BASE` was
`STACK_TOP - 0x500`, which is inside the dropped band but BELOW `STACK_TOP - STACK_SCRATCH` — the
address at which the kit stops reading a write as a call frame's own and starts reading it as
program output (`tools/recreate_kit/oracle/emu.py`). The battery's pin asserted the dropped band and
not that, so nothing said so. The base is now exactly `STACK_TOP - STACK_SCRATCH`, the assertion is
there, and the three spans are ordered with the vfprintf BUFFER last: it is the one with no bound on
what is written into it, so it overruns into unused band rather than onto `c_fcvt`'s working double —
which is the direction the original overruns too.

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
| `0x10116` | `crt0_setup_args` | 2 | ✅ verified | a bare `rts` — the Alcyon runtime's argv hook, stubbed out at link time. Run to `rts` with the command tail the crt0 pushes staged, and the ORACLE'S WRITE-SET asserted EMPTY: the byte diff alone would be vacuous (two programs that do nothing agree), so what carries the case is that the original writes no memory. Filed here rather than under `init` because it is the C library's hook and not the game's boot chain |
| `0x1683e` | `c_strlen` | 41 | ✅ verified | 5 strings incl. empty and 199 bytes; D0 compared as a longword |
| `0x167fc` | `c_strcmp` | 66 | ✅ verified | 10 pairs incl. three high-bit ones — the bytes are SIGN-extended, so an unsigned port returns the opposite sign |
| `0x158fe` | `c_ldiv` | 114 | ✅ verified | stub-driven; 10 edge pairs with attribution poison + 8 x 24 fuzz pairs. Both answers land in the caller's slots. The ZERO DIVISOR is three more cases, run with the machine's zero-divide vector declared (see the residual), plus one that pins the oracle refusing the run without it |
| `0x15970` | `c_lmul` | 108 | ✅ verified | stub-driven; 11 edge pairs with poison + 8 x 24 fuzz pairs. It eats four of its own eight argument bytes |
| `0x15cae` | `c_setfdmode` | 76 | ✅ verified | 5 tables incl. a FULL one, where the record is silently dropped |
| `0x15cfa` | `c_clearfdmode` | 60 | ✅ verified | 5 handles over a table holding one twice — both copies are cleared |
| `0x15d36` | `c_getfdmode` | 46 | ✅ verified | 4 handles, one of them ABSENT: the miss reads past the table onto `A_c_malloc_freelist`, staged with random bytes so a plausible 0 would fail |
| `0x15e58` | `gemdos_trap` | 28 | ✅ verified | through every wrapper below: the three save slots are staged with noise and diffed, and the `RET_*` says which site ran |
| `0x15e3c` | `xbios_trap` | 28 | ✅ verified | entered directly with XBIOS Physbase (0x02); D0 = `OS_SCREEN_BASE` and the slots hold the harness's own sentinel |
| `0x15c82` | `gemdos_malloc` | 22 | ✅ verified | 6 sizes (D0 = the modeled arena base) plus the `Malloc(-1)` query, which answers the free window and allocates nothing; and the save slots |
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
| `0x1518c` | `fp_cmp` **(entered at** `0x15190` **)** | 66 | ✅ verified | 9 pairs; its ONLY output is `A_fp_ccr`, the whole SR — see the residual on its high byte. The routine opens with TWO `link a6,#$0`, and `fp_op_table[4]` points at the SECOND (0x15190) — so that is where the case enters, while the row is filed at the address `../names.txt` names |
| `0x153fe` | `fp_dispatch` | 178 | ✅ verified | 5 double-source opcodes + 6 widening ones, plus the whole `Random() -> 5..15` chain the front end computes, run as five C calls from one stub |
| `0x14d72` | `c_fclose` | 82 | ✅ verified | 4 flag sets incl. a free slot and a GEMDOS-allocated buffer; whether the flush leaves A1 elsewhere is derived from the record BEFORE it runs |
| `0x14dc4` | `c_fflush` | 188 | ✅ verified | a free slot, 5 dirty buffers (binary, text, append, read-write, empty) and 4 read ones — where the GEMDOS cursor seeks BACK over what was never handed out |
| `0x14e80` | `c_filbuf` | 304 | ✅ verified | 5 stream shapes over a staged file, 3 refusals (EOF, ERR, write-only), end of file, and one OFF-STRIDE record — the only way to see `divs.w`'s remainder land in the high word |
| `0x14fb0` | `c_flsbuf` | 318 | ✅ verified | 8 (byte, flags, buffer state) rows: the line-buffered arm that returns WITHOUT flushing, the newline and full-buffer arms that do, unbuffered, fully buffered, and both error arms |
| `0x150ee` | `c_putc` | 68 | ✅ verified | 3 counts incl. 0, where the pre-decrement is what sends it to c_flsbuf with -1 already stored |
| `0x15588` | `c_fcvt` | 346 | ✅ verified | 16 doubles x 3 digit counts, compared as BYTES; the scaling loop, the ×10-by-shift-and-add digit loop, the round-half-up carry and the leading-zero shift |
| `0x156e2` | `c_fopen` | 406 | ✅ verified | 8 mode strings over r/w/a/+/b, 5 it refuses (including `"rb"`, which does not parse — the 'b' is a PREFIX), the slot hint and an out-of-range hint |
| `0x15878` | `c_fread` | 134 | ✅ verified | 6 (size, items, buffered) rows: out of the buffer, through c_filbuf, past end of file where the answer is a division, and a partial record the division drops |
| `0x159dc` | `c_lseek` | 278 | ✅ verified | 6 (offset, whence) rows incl. one past the staged length into the reserved capacity, and 3 pseudo-handles answered -1 without a trap |
| `0x1620c` | `c_doprnt` | 650 | ✅ verified | 45 formats over every conversion and flag the engine has + 8 x 24 fuzzed ones + the two extreme exponents + 4 trailing-`%` cases, which dispatch on the CALLER'S D7 |
| `0x15e74` | `c_fmt_integer` | 364 | ✅ verified | 12 (conversion, long, value) rows across all four bases and both sign rules, plus 5 that reach the arm where the BASE is the caller's D7 — which `c_doprnt` never takes |
| `0x15fe0` | `c_fmt_float` | 472 | ✅ verified | 3 conversions x 8 (precision, value) rows, incl. the 0x100 "no precision" sentinel and both zeroes; `%g` proves it takes the `%e` path |
| `0x161b8` | `c_fmt_getnum` | 84 | ✅ verified | 10 strings incl. an empty one, a 16-bit wrap and a high-bit byte, which the SIGN-extended compare puts below '0' |
| `0x164c2` | `c_printf` | 22 | ✅ verified | 2 formats onto a LINE-BUFFERED CON: `c_stdout`, so the whole chain down to the console ledger runs |
| `0x164d8` | `c_sprintf` | 22 | ✅ verified | one format, entered so that `argp` is its own second argument slot — the list c_doprnt walks |
| `0x16496` | `c_vfprintf` | 44 | ✅ verified | 3 formats, incl. the game's own message; the 256-byte buffer is stack on both sides, so what is compared is what c_fputs pushes out of it |
| `0x164ee` | `c_fputs` | 42 | ✅ verified | 4 strings incl. one that overflows the stream's buffer mid-string and flushes through c_write |
| `0x16518` | `c_conin` | 356 | ✅ verified | 8 typed lines (RETURN, BACKSPACE with and without anything to rub out, the end-of-file character, a typed LINE FEED) + 4 already-gathered lines + 3 refused handles. Every echo is a console-ledger entry with its own RET_* |
| `0x16b5e` | `c_conout_write` | 74 | ✅ verified | 7 spans incl. an empty one, a partial one and every printable byte; the ledger is the whole surface, and the zero-length case asserts an EMPTY ledger so "never ran" cannot pass as "wrote nothing" |
| `0x16c04` | `c_write` | 394 | ✅ verified | 6 binary spans, 7 text ones over every newline position, and 3 to CON:. The three Fwrite sites leave different RET_*, so the run, the CR/LF pair and the tail are told apart by more than the file's bytes |

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
* **`gemdos_malloc_or_fail`'s failure arm (Malloc returned 0 → -1) is unreachable IN A GREEN CASE**:
  the modeled `os_malloc` is a bump allocator that succeeds until the arena's ceiling, and the one
  way to get its 0 — a request the `[0x30000, 0x90000)` window cannot hold — comes back through
  `os_refused`, which reddens the run rather than exercising the arm. Read-verified, as is
  `c_morecore`'s and `c_malloc`'s handling of it.
* **`c_open`'s and `c_creat`'s "GEMDOS refused" arms are unreachable** for the same kind of reason:
  `os_fopen` REFUSES an unstaged name rather than returning a negative handle, so a case that asked
  for one would be rejected instead of exercising the arm. Read-verified.
* **`c_open`'s truncating arm (`mode & 1`) calls `c_unlink` @ 0x16868 = GEMDOS Fdelete**, which the
  kit does not model. The reconstruction routes it through `os_refused`, so a case reaching it fails
  loudly. Nothing in the game asks for it — `c_creat` requests write access only.
* **`c_read`'s console arm** (a handle at or below `FD_DEVICE_CON`) is still not reconstructed and
  still refuses — but the reason has changed and is now scope rather than a model gap. Its body is a
  loop calling `c_conin` @ 0x16518 once per byte until the count runs out or one answers -1, and
  `c_conin` is verified above. Porting it is ordinary work on an already-verified routine, and it is
  the natural next thing in this subsystem.
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
* **`c_lseek`'s FAILURE PATH is read-verified and cannot be otherwise.** When GEMDOS refuses a seek,
  the original asks for the current position and the file's length, re-bases the offset, EXTENDS the
  file by `Fwrite`ing `offset - length` bytes read off its OWN UNINITIALISED STACK FRAME, and seeks
  again. Two things stop it being a case: the trap model refuses a seek it cannot serve rather than
  answering an error code (TRAP_MODEL.md, Phase 13, "a refusal is not an error return"), so the first
  seek never comes back negative in a green run; and the bytes that would reach the file are frame
  garbage no reconstruction can produce. The four `RET_*` of that path are named in `include/clib.h`
  and the arithmetic is described there; nothing is transcribed against nothing.
* **THE RECONSTRUCTION KEEPS TWO PIECES OF SCRATCH IN THE IMAGE THAT THE ORIGINAL KEEPS ON ITS
  STACK**, and neither is pinned. `c_fcvt` scales its working copy of a double with `fp_mul`/`fp_div`,
  which take IMAGE addresses, and `c_vfprintf` formats into a 256-byte buffer that `c_fputs` then
  walks by address; the originals are `-14(a6)` and `-256(a6)`. A reconstruction has no frame in the
  image, so `include/clib.h` names three spans at `CLIB_SCRATCH_BASE` — inside the band the
  differential DROPS as stack, which is where the original's are too. A candidate that used different
  in-band addresses would still be green. What IS pinned is what each produces: `A_fp_acc` and the
  digits `c_fcvt` hands back, and the bytes `c_fputs` pushes into the FILE.
* **`c_fmt_float`'s digit buffer is a C array, not the original's 30-byte frame.** The original
  writes `precision + 3` digits into `-30(a6)` and would smash its own frame somewhere past a
  precision of about 25; the reconstruction holds them in `C_FCVT_DIGITS_MAX` bytes and the battery
  stays inside the range the original survives. The overflow is read-verified, not reproduced.
  `c_vfprintf`'s 256-byte buffer has the same shape of limit and the same answer.
* **`c_fmt_integer`'s "unknown conversion" arm formats in a base of the CALLER'S making.** The
  four-way chain leaves D7 alone when the conversion is none of d/u/o/x, so the base is whatever the
  caller left there — and from `c_doprnt` that is the conversion character itself. `c_doprnt` only
  ever routes d/u/o/x here, so nothing in the program reaches it; five cases declare the register and
  run it anyway, including bases this library cannot name.
* **`c_doprnt`'s trailing bare `%` dispatches on D7 for the same reason**, and four cases declare it
  ('d', 's', 'f' and 0 — each consuming a different number of argument bytes). Both are §5
  "a parameter" residuals: real branches, reachable only by declaring a register the C ABI has no
  name for.
* **`c_filbuf` @ 0x14eac..0x14eb2 is DEAD CODE.** Nothing branches there; the two stores it holds
  (ptr = base, cnt = 0) are the compiler's leftovers from a path the optimiser removed. Transcribed
  as a comment rather than as code.
* **`c_filbuf`'s stdout flush is unreachable under the model.** It fires only for a stream whose
  handle is `FD_DEVICE_CON`, and `c_read` — called two lines later — refuses that handle, so every
  run that reaches the flush is voided before it ends. Read-verified; closing it means porting
  `c_read`'s console arm, which `c_conin` has now unblocked (see the residual above).
* **THE A1 A CALL LEAVES BEHIND IS CARRIED, NOT PREDICTED.** `c_getfdmode` comes back with A1 one
  entry past the fd-mode table (= `A_c_errno`) and nothing puts it back, so every trap the CALLER
  reaches afterwards files that rather than what it held before. `c_read` and `c_write` are the only
  two routines that ask, so they are the only two that record it — into a register block the whole
  buffered layer carries BY POINTER (`c_read_reporting` / `c_write_reporting`; the by-value spellings
  remain for callers outside this subsystem). Predicting it per caller was the first shape here and
  it was wrong: `c_fputs`'s second flush files a different A1 from its first, which
  `test_c_fputs_across_several_flushes` is the case for.
* **Two of the three out-of-bounds guards refuse input the ORIGINAL does not survive either.** A
  precision above 60 and a negative one are refused by `c_fmt_float`, and a base needing more than
  `FMT_DIGIT_SLOTS` digits by `c_fmt_integer` — all three well outside anything the original's own
  frames hold. Refusing is not the original's behaviour; the original corrupts its frame and carries
  on. That is recorded here rather than reproduced, because reproducing it means writing outside a C
  array in the harness's process.

### Not ported, and what each would need

Five wrappers, one unmodeled GEMDOS call each. Every other routine in this subsystem is verified
above; none of these five is reachable in play.

| Routine | Why | What would close it |
|---|---|---|
| `c_unlink` @ 0x16868 | GEMDOS **Fdelete (0x41)**, unmodeled | clearing a staged slot's name (or its open flag) and answering 0/-1. One site, and only `c_open`'s truncating arm reaches it — which `c_creat` never asks for |
| `c_exit_pterm` @ 0x14d16 | GEMDOS **Pterm (0x4c)**, unmodeled and unmodelable as a return | nothing: a run that terminates has no `rts` to diff at. Record it read-verified |
| `c_exit` @ 0x14d2c | walks the 73 `c_iob` records calling `c_fclose` on every one whose flags & 3 is set, then `c_exit_pterm` | the walk is now ordinary work — `c_fclose` is verified — but the tail is Pterm, so it wants a `stop_pc` checkpoint at the call rather than a model for it. `c_conin`'s ^C arm is the other caller, and refuses for the same reason |
| `c_auxout_write` @ 0x16ba8 | GEMDOS **Cauxout (0x04)**, unmodeled | an `OS_EVENT_CONOUT`-shaped ledger kind per device. `c_write`'s AUX: arm refuses until then |
| `c_prtout_write` @ 0x16bd6 | GEMDOS **Cprnout (0x05)**, unmodeled | the same, for PRT:. `c_conin`'s AUX: arm wants **Cauxin (0x03)** on the read side and refuses likewise |

## Borrowed globals

A global lives in the header of the subsystem that owns the data (README.md, "Adding a function").
A row here is a LOAN: a global defined in a header that does not own it, because the routine that
does is unported. Each row names the address, the name as spelt, the owner, where it is defined
today, and why — and a finished migration DELETES its row and the `#define` it names, so the
table's length reads as outstanding debt rather than as history.

| Addr | Name | Owner | Defined in | Why on loan |
|---|---|---|---|---|
| `0x25182` / `0x2518a` / `0x25192` | `A_const_mouse_x_scale_room35` / `A_const_mouse_x_scale` / `A_const_mouse_y_scale` | clib (the DATA the fp package divides by) | `include/gameplay.h` | three doubles in the program's DATA segment. `include/clib.h` owns the float package but names none of the program's own constants; if it grows a home for them, these three rows and their defines go |

**ONE ROW IS LEFT, AND THAT IS THE CONTRACT WORKING.** This table has carried nine rows and has
retired eight, each by the edit its own "Why on loan" column named in advance:

* `A_room_number`, `A_object_table` and `A_room_table` were `include/blit.h`'s while the gameplay
  subsystem was unported. `include/gameplay.h` defines all three now, plus the `OBJECT_*` / `ROOM_*`
  record offsets that moved with them, and `src/blit.c` includes it to read them.
* `A_key_raw`, `A_key_shift_state`, `A_mouse_y`, `A_mouse_x` and `A_mouse_buttons` — the input block
  — were `include/gameplay.h`'s while the front end's VDI binding was unported. `include/frontend.h`
  defines all five now (the routines that FILL them are `vq_mouse` @ 0x16a26, `vq_key_s` @ 0x16a5e
  and the `Crawio(0xff)` poll, all that subsystem's), and `src/gameplay.c` includes it to read them.
  `A_key_raw` is written from `game_frame_update` @ 0x1238e — a writer in another subsystem, but one
  word of one block, and a block has one owner.
* `A_sound_enabled` had a row and should not have: the routine that WRITES it is
  `game_frame_update`'s `^S` arm @ 0x123ea, which is the gameplay subsystem's own, so gameplay owns
  it and never borrowed it. `title_menu_loop` @ 0x115d6 reads it too, and a reader in another
  subsystem is not ownership. The row is deleted as a misfiling rather than as a migration.

Rows are DELETED rather than annotated, so the table's length reads as outstanding debt and not as
history. What is left is the three doubles ABOVE, and their row says what would retire them.

**What the two checks do and do not cover, for the record offsets that travel with a table.** An
offset re-defined under the SAME name in two headers IS caught — `test_no_constant_is_defined_in_two_files`
is keyed on the name and takes offsets as readily as addresses. What is NOT caught is the same
offset under a DIFFERENT name: `OBJECT_TILE` in one header and, say, `OBJ_TILE_INDEX` in another,
both 0. `test_no_address_has_two_spellings` is value-keyed but only over the `A_*` family,
deliberately — for geometry and record offsets a shared VALUE carries no information at all
(`OBJECT_TILE` and `MFDB_ADDR` are both 0 and always will be), so a value-keyed check over these
families would fire on coincidences and be turned off. So the differently-named duplicate is the
case that has to be caught by reading, and the provenance tag on every `OBJECT_*` / `ROOM_*` /
`CANDLE_*` / `PROBE_*` line in `include/gameplay.h` — the `lea`/`muls` instruction each offset was
read off, and the case that pins it — is what makes that reading cheap.

## Not reconstructed, and why

Every `fn` line in `../names.txt` with no ✅ row above eventually appears here, with the reason:
unreachable under the model, a model gap named above, or simply not yet started. Each ported section
defers a named set; those sets are gathered here so that "what is left" is one list rather than
several asides.

**Read the "not blocked any more" rows first.** TRAP_MODEL.md phases 11-13 and the front end's GEM
binding between them retired five of this table's reasons in one wave, and a row that still reads
like a gap when it has become ordinary work is the most expensive kind of stale prose here.

| Routine(s) | Subsystem | Why not, and what would close it |
|---|---|---|
| `load_voice_player` @ 0x13c6c, `play_voice` @ 0x13cea | sound | The digitised-voice path (`GHOST.LOA`): a second program `jsr`ed inside the BSS that programs MFP Timer A and busy-waits. Needs the timer/busy-wait gap in "Model gaps" closed first; it has nothing to do with the engine that IS ported |
| `c_unlink` @ 0x16868, `c_exit_pterm` @ 0x14d16, `c_exit` @ 0x14d2c, `c_auxout_write` @ 0x16ba8, `c_prtout_write` @ 0x16bd6 | clib | **The whole C library except these five.** One unmodeled GEMDOS call each — Fdelete (0x41), Pterm (0x4c) twice over, Cauxout (0x04), Cprnout (0x05) — and `c_conin`'s AUX: arm wants Cauxin (0x03) on the read side. The clib section's table says what each would need; none of the five is reachable in play |
| `hud_draw_counters` @ 0x113d2, `hud_bonus_bar_fill` @ 0x112c8, `hud_bonus_bar_shrink` @ 0x11346 | gameplay | **NOT BLOCKED ANY MORE — this row is now just work.** All three reach the game's own VDI binding (`vst_height`, `vst_color`, `vsf_color`, `v_gtext`, `vr_recfl`, and `vdi_call` behind them), which was the front end's and unported; it is ported and verified, so `#include "frontend.h"` and call it — `include/frontend.h` also carries `A_blit_pxy`, the rectangle `vr_recfl` is handed. Two things they still need: the CALLER's A1/A2, which every routine in that binding takes as an argument, and — for `hud_bonus_bar_fill`, which reaches `vdi_call` from inside a loop that has already reloaded A2 — a register that is derivable rather than an entry argument (`docs/agent-playbook.md` §5) |
| `game_frame_update`'s front-end poll `[0x1233a, 0x12434)` | gameplay | **NEITHER HALF IS BLOCKED ANY MORE.** `vq_mouse` @ 0x16a26 and `vq_key_s` @ 0x16a5e are verified in `## Verified — frontend` and callable from here; the `Crawio(0xff)` key read between them at `[0x12360, 0x12434)` was never blocked (`Cconis`/`Crawcin`/`Cnecin` are modeled and `harness.console_keys()` stages a QUEUE the run drains, so even the `^P` pause is drivable). It is simply not done: it wants a slice entered at 0x1233a, the three trampoline save slots per trap, and a decision about the `^S` and `^R` arms' whole-game reset. Ordinary porting work, and the natural next thing in this subsystem |
| `game_frame_update`'s death sequence `[0x1273c, 0x1294a)` | gameplay | **NOT BLOCKED ANY MORE.** The pop/respawn animation calls `save_sprite_backgrounds` / `draw_sprites` / `restore_sprite_backgrounds` five times over, and all three are verified in `## Verified — frontend` (they moved there with the sprite protocol). The `Random()` it runs through the fp package and the two-player save at 0x128c8 were never gaps |
| `crt0_start` @ 0x10036, `init_globals` @ 0x16d8e, `main` @ 0x100dc, `game_top_loop` @ 0x101e6 | init | Not started; each is a slice rather than a function (see that section). `main`'s wrong-resolution arm reaches `c_printf`, which is verified now, so that arm is ordinary work; `game_top_loop` never returns, and the two `Bconout` IKBD commands that used to block it are modeled now — what is left is a chain of slices between calls that are themselves verified |
| `title_menu_loop` @ 0x115d6 and the demo player at 0x11992 | frontend | Not started, and no longer blocked on the model: `harness.console_keys` stages up to eight keystrokes in order, which is exactly the menu's `while (Cconis()) Crawcin(); c = Cnecin()` idiom. The `[D]` attract path polls `vq_mouse` 37,000 times and drives the fp package for its two `Random()` ranges — both verified — so what it needs is a mid-entry slice per menu branch and an instruction cap that fits |
