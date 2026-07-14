# Reconstruction status — BuggyBoy

Human-readable C reconstruction of all 91 functions, each **verified byte-for-byte
against the original 68000 code** by the differential harness (Musashi oracle vs the
compiled reconstruction). See [`README.md`](README.md) for how it works.

**Verified: 74/91.**

## Method per function
1. Read the target in `../decomp.c` + the real disassembly (`prg_dis.py`) to fix semantics.
2. Write the idiomatic core in `src/<subsystem>.c` and its glue `g_<name>` (the I/O contract).
3. Add address constants to `include/addrs.h`, prototypes to `include/buggyboy.h`.
4. Add a fuzz + edge-case test in `test/test_<subsystem>.py`; `make test` must be green.
5. Mark the row below verified.

## Ordering
Prefer leaf/pure functions first (no OS traps, simple contracts), then their callers, then
trap-bound functions (GEMDOS/BIOS/XBIOS/AES/VDI) once deterministic trap stubs exist. Note
several 2–4 byte "functions" are fall-through entry aliases (e.g. `fill_words`→`fill_span`,
`draw_text`→`draw_text_row`); port them with their target.

## Functions (by address)

| Addr (Ghidra) | Name | Bytes | Status | Verification |
|---------------|------|-------|--------|--------------|
| `0x10000` | `_start` | 220 | ✅ verified | checkpoint @0x100d4 (GEM init; before `bsr main`) |
| `0x100dc` | `gem_aes` | 14 | ✅ verified | trap #2 AES (appl_init + graf_handle) |
| `0x100ea` | `gem_vdi` | 12 | ✅ verified | trap #2 VDI (v_opnvwk) |
| `0x10100` | `main` | 494 | ✅ verified | checkpoint @0x10144 (Malloc + the five buffer pointers) |
| `0x102ee` | `wait_vbl_set_offset` | 18 | ✅ verified | 51x Vsync (hardware) then set_screen_offset body |
| `0x10300` | `set_screen_offset` | 38 | ✅ verified | leg 0-4 x frame 0-15 (scroll-table byte * 0x1900 -> screen_offset) |
| `0x10326` | `blit_road_scroll` | 340 | ✅ verified | hscroll sweep (shift/coarse/edge) + delta fuzz; rol.l fine-scroll + wrap seam + top fill |
| `0x1047a` | `init_scoretable` | 62 | ✅ verified | 6-seed noise + poison (5 legs x 9 default rows from A_default_scores) |
| `0x104b8` | `init_leg` | 360 |  |  |
| `0x10620` | `unpack_graphics` | 364 | ✅ verified | run-to-rts (decode + deinterleave + sprite tables) |
| `0x1078c` | `build_sprite_shifts` | 102 | ✅ verified | fuzz counts 0/3/0xcf (asr.l shifts) |
| `0x107f2` | `build_sprite_shifts_msk` | 140 | ✅ verified | fuzz over the 7 real (D0/D1/D5) configs |
| `0x1087e` | `draw_object` | 862 |  |  |
| `0x10bdc` | `blit_obj_Ln` | 126 | ✅ verified | 1500-seed fuzz (pixels + D0.w) |
| `0x10c5a` | `blit_obj_Rn` | 126 | ✅ verified | 1500-fuzz pixels |
| `0x10cd8` | `blit_obj_Ln2` | 142 | ✅ verified | 300-fuzz pixels (road walk) |
| `0x10d66` | `blit_obj_Rn2` | 142 | ✅ verified | 300-fuzz pixels (road walk) |
| `0x10df4` | `blit_obj_Lf` | 112 | ✅ verified | 1500-fuzz pixels |
| `0x10e64` | `blit_obj_Rf` | 106 | ✅ verified | 1500-fuzz pixels |
| `0x10ece` | `blit_obj_Lf2` | 146 | ✅ verified | 300-fuzz pixels (road walk) |
| `0x10f60` | `blit_obj_Rf2` | 146 | ✅ verified | 300-fuzz pixels (road walk) |
| `0x10ff2` | `draw_ground` | 178 |  |  |
| `0x110a4` | `probe_collision` | 106 | ✅ verified | fuzz marker (y/bit/x) x random bitmap + zero-bitmap no-hit (8-neighbour dashboard probe) |
| `0x1110e` | `game_update` | 2452 |  |  |
| `0x11ba4` | `evt_flag_gate` | 104 | ✅ verified | fuzz: 5 entries x seq/bonus/slot (add_score + play_event_tune) |
| `0x11c2c` | `evt_collision` | 46 | ✅ verified | fuzz lock x rpm (rpm floor + speed) |
| `0x11c5a` | `evt_score_msg` | 24 | ✅ verified | fuzz d6/d7 (add_score + play_event_tune) |
| `0x11c7a` | `play_event_tune` | 56 | ✅ verified | fuzz over/cur/MZFLAG/tune (-> INITTUNE) |
| `0x11cb2` | `handle_marker` | 42 | ✅ verified | fuzz over/cur/MZFLAG/fx (-> TURNOFF/INITFX) |
| `0x11f4c` | `build_road_geometry` | 356 | ✅ verified | 300-seed fuzz (whole-image) |
| `0x120b0` | `read_input` | 70 | ✅ verified | fuzz input_state x last_key (joystick keep vs keyboard-scancode map) |
| `0x120f8` | `set_rez` | 24 | ✅ verified | trap layer (Ikbdws); D0.b -> config byte |
| `0x12110` | `read_joystick` | 20 | ✅ verified | run-to-rts (IKBD status modeled TDRE-ready; no image effect) |
| `0x12124` | `install_handlers` | 50 | ✅ verified | run-to-rts; Kbdvbase modeled, saves + patches mousevec/joyvec vectors |
| `0x12166` | `load_graphics` | 146 | ✅ verified | checkpoint @0x121f2 (both Freads; before unpack) |
| `0x121f8` | `flip_screen` | 46 | ✅ verified | flip_idx fuzz past {0,4}; video base + Vsync hardware-only, toggle observable |
| `0x12226` | `xbios_setscreen` | 26 | ✅ verified | trap layer; no image effect |
| `0x1225a` | `draw_results_screen` | 308 | ✅ verified | orchestrator; mode/pos/leg x flip (A3 + A0/fill chaining) |
| `0x1238e` | `update_highscore` | 612 | ✅ verified | checkpoints 0x12450 (made) / 0x123e6 (miss): EGOFF + rank + shift + insert; name-entry loop read-only |
| `0x125f2` | `draw_leg_results` | 244 | ✅ verified | orchestrator; leg 0/1/2/4 x flip (fills + panels + labels + dashboard) |
| `0x126e6` | `draw_divider` | 54 | ✅ verified | flip 0/4 (fill_rect + two vertical lines) |
| `0x1271c` | `draw_panel5` | 60 | ✅ verified | flip 0/4 (divider + 5 chained labels) |
| `0x12758` | `draw_panel3` | 40 | ✅ verified | flip 0/4 (divider + 3 chained labels) |
| `0x12780` | `draw_panel2` | 32 | ✅ verified | flip 0/4 (divider + 2 chained labels) |
| `0x127a0` | `intermission` | 330 |  |  |
| `0x128ea` | `check_abort` | 42 | ✅ verified | return-value fuzz (abort code vs swap(Crawio)); GEMDOS 6 modeled |
| `0x12914` | `intermission_poll` | 86 | ✅ verified | 25-seed fuzz x flip (9-entry table-driven block blit; not input) |
| `0x129a0` | `fade_step` | 26 |  |  |
| `0x129ba` | `draw_intermission` | 316 |  |  |
| `0x12af6` | `init_playfield` | 578 |  |  |
| `0x12d38` | `init_leg_dash` | 80 | ✅ verified | leg 0-4 x 6-seed fuzz (marker seed + pixel-doubled dashboard build) |
| `0x12d88` | `draw_leg_labels` | 154 | ✅ verified | leg 0-4 fuzz + empty-label edge (glyph AND/OR blit + 4-row clear -> probe_collision) |
| `0x12e22` | `draw_frame` | 22 |  |  |
| `0x12e38` | `clear_screen` | 30 | ✅ verified | flip 0/4 |
| `0x12e56` | `fill_screen` | 4 | ✅ verified | flip 0/4 x colours |
| `0x12e5a` | `fill_words` | 2 | ✅ verified | 500-seed fuzz |
| `0x12e5c` | `fill_span` | 36 | ✅ verified | 500-seed fuzz |
| `0x12e80` | `fill_rect` | 48 | ✅ verified | 500-seed fuzz + stride check |
| `0x12eb0` | `xbios_setpalette` | 12 | ✅ verified | trap layer; no image effect |
| `0x12ebc` | `stop_music_chk` | 8 | ✅ verified | guard fuzz (MZFLAG gate + game_over); falls into stop_music |
| `0x12ec4` | `stop_music` | 50 | ✅ verified | guard fuzz (game_over); TURNOFF + clear fx/tune/vec + XBIOS Dosound (0x20) |
| `0x12ef6` | `draw_game_objects` | 376 |  |  |
| `0x1306e` | `draw_object_list` | 214 |  |  |
| `0x1442c` | `draw_checkpoint_anim` | 118 |  |  |
| `0x15016` | `draw_result_row` | 86 | ✅ verified | 300-fuzz (buf_c src -> buffer; 4-word transparency blit) |
| `0x1506c` | `draw_result_col` | 56 | ✅ verified | 300-fuzz (buf_c src -> buffer; 5x tiled copy) |
| `0x150a4` | `draw_dashboard` | 230 | ✅ verified | 200-fuzz (buf_c graphic -> buffer; 40x8 masked blit) |
| `0x1518a` | `draw_fg_sprite` | 108 | ✅ verified | spin/curve gate + anim table; falls into wheels |
| `0x151f6` | `draw_buggy_wheels` | 182 | ✅ verified | fuzz A0/A1/D4 (4-cell transparency blit, walks up) |
| `0x152ac` | `draw_buggy` | 334 |  |  |
| `0x153fa` | `draw_buggy_lo` | 204 | ✅ verified | A6=buffer; gated 2-sub-sprite piece-list body |
| `0x154c6` | `draw_buggy_hi` | 152 | ✅ verified | A2=dst; lean overlay OR-blit + speed-anim counter |
| `0x1555e` | `draw_hud` | 684 |  |  |
| `0x1580a` | `add_score` | 104 | ✅ verified | 2000-seed fuzz + edge cases |
| `0x15872` | `draw_crash_fx` | 392 |  |  |
| `0x159fa` | `draw_text` | 2 | ✅ verified | count-preset entry alias of `draw_text_row` |
| `0x159fc` | `draw_text_row` | 12 | ✅ verified | fuzz char pairs x colour x flip (shared body) |
| `0x15a08` | `draw_hud_gauge0` | 28 | ✅ verified | fuzz: absolute-A0 entry (skips D0->buffer) |
| `0x15a24` | `draw_hud_bar` | 96 | ✅ verified | fuzz: A0 + preset D2/D3 fill entry |
| `0x15a84` | `draw_num_thunk` | 2 | ✅ verified | count-preset entry alias of `draw_num` |
| `0x15a86` | `draw_num` | 112 | ✅ verified | fuzz digits x colour x flip (buf_c sprite staging) |
| `0x15af6` | `render_road` | 4 |  |  |
| `0x19144` | `render_road` | 2256 |  |  |
| `0x1b252` | `EGOFF` | 16 | ✅ verified | run-to-rts (clear EGFLAG + music byte) |
| `0x1b268` | `TURNOFF` | 20 | ✅ verified | run-to-rts |
| `0x1b2e8` | `snd_voice_a` | 4 | ✅ verified | +0x18 entry alias of `snd_voice_b` |
| `0x1b2ec` | `snd_voice_b` | 160 | ✅ verified | fuzz glide/note/pitch + 13-cmd table (0x88 excluded) |
| `0x1b3ba` | `snd_stub` | 4 | ✅ verified | +0x18 entry alias of `snd_cmd_handler` |
| `0x1b3be` | `snd_cmd_handler` | 244 | ✅ verified | 400-seed fuzz (image + returned D1 period) |
| `0x1b560` | `INITFX` | 60 | ✅ verified | fuzz fx id |
| `0x1b59c` | `INITTUNE` | 86 | ✅ verified | fuzz tune id |

## Verification notes

Surfaced by the high-effort code review; the harness itself was hardened (truncation raises; a
stray write in the guard band fails loudly; exclude bands are vetted against the stack extent;
leaf tests can run an attribution/poison pass; the ISA is cross-validated against a real 68000).
Two coverage gaps from the original list are now **closed**: `fill_span`/`fill_rect` fuzz both
`flip_idx` slots (not just 0), and the road-walk (`*2`) fuzz spans a wider x-offset range
(−800..1200) so the walk itself drives all of `row_left`/`row_right`'s edge regimes (off-edge,
fully-inside, straddling), not just the straddle. Remaining, low-severity:

- **Blit return register (D0)** — *blocked on `draw_object`, not just deferred.* Only `Ln`'s status
  word is a clean, standalone-verifiable return. `Lf`/`Rf` and the `*2` variants leave a D0 that is
  an internal leftover meaningful only to the caller — an `Lf`-vs-oracle spot-check mismatches ~15%
  of the time — so it can be pinned only once `draw_object` (the caller) is reconstructed. Pixels
  are fully diffed for every variant; only the returned register is unverified.
- **`_start` past `bsr main`** — *inherent (unreachable).* The terminal Pterm / `appl_exit` after
  `main` never execute (`main` is the infinite game loop), so they can't be verified by execution —
  only by reading. Everything up to the `0x100d4` checkpoint is diffed.
- **snd_voice command 0x88 ("end tune")** — this command rewrites the return address on the stack
  to re-enter REFRESH (`0x1b0f0`) after a TURNOFF, so it cannot be verified by a bare run-to-rts
  diff of `snd_voice_step` alone (the leaf fuzz builds streams from the 12 other commands + notes).
  Its full behaviour is instead verified through **REFRESH**: `snd_voice_step` returns an "ended"
  flag, REFRESH aborts the rest of the frame on it, and `test_refresh_music` (tune 8) exercises the
  path. Residual: only a voice-0 end is seen there; a bug specific to a voice-1/2 end (the `||`
  short-circuit order) is not independently covered. The stepper also assumes D0's high byte is 0
  (a design invariant: it indexes a 256-entry byte table and a 13-entry jump table).

## Checkpoint verification

A function that never returns can't be run to `rts`, so the harness can also stop at a
**checkpoint PC** and diff the image there (`emu.run(..., stop_pc=)`, `differential(..., stop_pc=,
exclude=)`). `_start` is verified this way at `0x100d4` (the `bsr main`); its GEM init is fully
diffed while `main` — the infinite game loop — is never entered. `main` itself is verified at
`0x10144` (its Malloc + the five buffer pointers, before the Supexec-wrapped init). `load_graphics`
is verified at `0x121f2` (before `bsr unpack_graphics`), diffing both file reads without the
decompressor. `exclude` drops a function's relocated-stack band from the diff (`_start` moves A7
to `0x1b044`; the reconstruction is pure C with no machine stack). Data-heavy functions raise
`differential(..., max_insns=)` (the unpacker needs a few million).

## Deferred: interactive (input/hardware-driven) functions

Some functions can't be run to `rts` under the current harness because their control flow is
driven by **live input or hardware** the oracle doesn't model. The input-driven family is now
handled by the IKBD memory model + scripted input globals (`HARNESS.md`): the leaves
`read_joystick` (`0x12110`), `read_input` (`0x120b0`) and `check_abort` (`0x128ea`) run to `rts`,
and `update_highscore` (`0x1238e`) is verified to a **checkpoint** — its deterministic prefix
(EGOFF + the score ranking, row shift and insert that populate `highscore_table`) is diffed at the
two exits (`0x12450` made / `0x123e6` missed), and the tail — the interactive name-entry loop that
busy-polls the IKBD, Vsyncs and waits on `MZFLAG` — is verified by reading, not execution (it can't
be run to `rts`). (`intermission_poll` (`0x12914`) was on this list by a wrong `# ctx` guess — it
reads no input; it's a table-driven block blit and is verified.) What was learnable by **reading**
`update_highscore`'s name-entry loop is captured in `names.txt`: `hiscore_pos` = the new score's
1-based rank; `results_mode` = 0 if it made the table (name entry) else 2; and `highscore_table`
(`0x18266`) is the row-2 source the results screen draws from.

## OS trap layer

OS-bound functions now run under the oracle: `trap #1/#13/#14/#2` are serviced by a
deterministic model (`include/os.h`, dispatched in `oracle/shim.c`). Calls that only touch
hardware/files (Setpalette/Setcolor/Setscreen, sound, console, Ikbdws) have no image effect;
Physbase/Logbase → OS_SCREEN_BASE, Malloc hands out a real in-image block from OS_HEAP_BASE
(sized for main's 0x5ee08-byte allocation); XBIOS Supexec runs the passed routine in place. **GEM trap #2** models the three AES/VDI calls BuggyBoy issues — AES
`appl_init`/`graf_handle`, VDI `v_opnvwk` — via `os_gem_trap()` (shared by the shim and the
reconstructed `gem_aes`/`gem_vdi`); realistic low-res values into the param block's `intout`.
**GEMDOS Fopen/Fread/Fclose** are modeled by `os_fopen`/`os_fread`/`os_fclose` over an in-image
staged-file table (the harness stages the real `COURSES.DAT`/`GRAPHICS.GRA` bytes; `IMAGE_SIZE`
is 1 MiB to hold them + the load buffers). Anything still not faithfully modeled (GEMDOS
**Super**, an **unmodeled GEM/VDI opcode**, an **unstaged file**, unknown fn) is counted and
`emu.run` **raises** — a function that hits one cannot be falsely "verified".

Unlocked next: the startup path (`_start` → `main` init → `load_graphics` → `unpack_graphics`)
and the course-event engine (`evt_*` / `handle_marker`) are verified, and the **sound driver** is
now fully reconstructed at the leaf level — the tune/effect setup (`TURNOFF`/`EGOFF`/`INITFX`/
`INITTUNE`), the per-voice note-stream stepper (`snd_voice_a/b`), and the per-frame voice DSP
(`snd_cmd_handler`/`snd_stub`). The VBL orchestrator **`REFRESH`** (`0x1b086`, not one of the 91
tracked functions) is now reconstructed too: it drives the three voices then dumps the YM2149
registers, verified per frame on **both** the memory image and the emitted PSG (reg,val) stream
(the oracle's shim taps the `$ffff8800/8802` writes; the reconstruction appends them to a buffer).
`test_refresh_music`/`_fx`/`_music_eg` seed real tracks/effects via INITTUNE/INITFX and step the
driver; the EG block is driven directly. That leaves the sound driver **complete**. Remaining
overall: the gameplay/draw/HUD families and the big orchestrators (`game_update`, `render_road`,
`draw_hud`).

## Oracle cross-validation

The differential suite trusts Musashi as ground truth; `oracle/isa_conformance.py` certifies that
trust against an **independent** 68000 — Hatari's WinUAE-derived core — so a Musashi quirk can't
masquerade as "verified". It runs **277** self-contained, position-independent instruction snippets
(inputs as immediates, flags captured with `move sr` right after the tested op, result saved via
`(a5)+`) on both cores and compares the 32-bit result + the *defined* CCR bits. Classes, chosen from
BuggyBoy's opcode mix: byte/word/long **memory RMW** (`addq/subq/neg/not/add` — the class that made
us reject Unicorn), `asr/lsr/lsl/rox/ro`, `ext`/`movea.w`, `muls/mulu/divs/divu`, `add/sub/addx/subx`,
`cmp.b`+`Scc`, `swap/neg`. **All 277 match.** The one divergence surfaced — N/Z after a `DIVS/DIVU`
overflow (Musashi 0, WinUAE 1) — is *undefined* per the 68000 PRM, so it is excluded from the CCR
comparison (the result and the defined V flag still agree). `test/test_isa_vs_tos.py` runs it,
skipping when Hatari or a TOS ROM is absent (the ROM isn't redistributable).
