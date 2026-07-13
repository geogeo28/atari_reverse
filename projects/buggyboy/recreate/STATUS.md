# Reconstruction status — BuggyBoy

Human-readable C reconstruction of all 91 functions, each **verified byte-for-byte
against the original 68000 code** by the differential harness (Musashi oracle vs the
compiled reconstruction). See [`README.md`](README.md) for how it works.

**Verified: 39/91.**

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
| `0x102ee` | `wait_vbl_set_offset` | 18 |  |  |
| `0x10300` | `set_screen_offset` | 38 |  |  |
| `0x10326` | `blit_road_scroll` | 340 |  |  |
| `0x1047a` | `init_scoretable` | 62 |  |  |
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
| `0x110a4` | `probe_collision` | 106 |  |  |
| `0x1110e` | `game_update` | 2452 |  |  |
| `0x11ba4` | `evt_flag_gate` | 104 | ✅ verified | fuzz: 5 entries x seq/bonus/slot (add_score + play_event_tune) |
| `0x11c2c` | `evt_collision` | 46 | ✅ verified | fuzz lock x rpm (rpm floor + speed) |
| `0x11c5a` | `evt_score_msg` | 24 | ✅ verified | fuzz d6/d7 (add_score + play_event_tune) |
| `0x11c7a` | `play_event_tune` | 56 | ✅ verified | fuzz over/cur/MZFLAG/tune (-> INITTUNE) |
| `0x11cb2` | `handle_marker` | 42 | ✅ verified | fuzz over/cur/MZFLAG/fx (-> TURNOFF/INITFX) |
| `0x11f4c` | `build_road_geometry` | 356 | ✅ verified | 300-seed fuzz (whole-image) |
| `0x120b0` | `read_input` | 70 |  |  |
| `0x120f8` | `set_rez` | 24 | ✅ verified | trap layer (Ikbdws); D0.b -> config byte |
| `0x12110` | `read_joystick` | 20 |  |  |
| `0x12124` | `install_handlers` | 50 |  |  |
| `0x12166` | `load_graphics` | 146 | ✅ verified | checkpoint @0x121f2 (both Freads; before unpack) |
| `0x121f8` | `flip_screen` | 46 |  |  |
| `0x12226` | `xbios_setscreen` | 26 | ✅ verified | trap layer; no image effect |
| `0x1225a` | `draw_results_screen` | 308 |  |  |
| `0x1238e` | `update_highscore` | 612 |  |  |
| `0x125f2` | `draw_leg_results` | 244 |  |  |
| `0x126e6` | `draw_divider` | 54 |  |  |
| `0x1271c` | `draw_panel5` | 60 |  |  |
| `0x12758` | `draw_panel3` | 40 |  |  |
| `0x12780` | `draw_panel2` | 32 |  |  |
| `0x127a0` | `intermission` | 330 |  |  |
| `0x128ea` | `check_abort` | 42 |  |  |
| `0x12914` | `intermission_poll` | 86 |  |  |
| `0x129a0` | `fade_step` | 26 |  |  |
| `0x129ba` | `draw_intermission` | 316 |  |  |
| `0x12af6` | `init_playfield` | 578 |  |  |
| `0x12d38` | `init_leg_dash` | 80 |  |  |
| `0x12d88` | `draw_leg_labels` | 154 |  |  |
| `0x12e22` | `draw_frame` | 22 |  |  |
| `0x12e38` | `clear_screen` | 30 | ✅ verified | flip 0/4 |
| `0x12e56` | `fill_screen` | 4 | ✅ verified | flip 0/4 x colours |
| `0x12e5a` | `fill_words` | 2 | ✅ verified | 500-seed fuzz |
| `0x12e5c` | `fill_span` | 36 | ✅ verified | 500-seed fuzz |
| `0x12e80` | `fill_rect` | 48 | ✅ verified | 500-seed fuzz + stride check |
| `0x12eb0` | `xbios_setpalette` | 12 | ✅ verified | trap layer; no image effect |
| `0x12ebc` | `stop_music_chk` | 8 |  |  |
| `0x12ec4` | `stop_music` | 50 |  |  |
| `0x12ef6` | `draw_game_objects` | 376 |  |  |
| `0x1306e` | `draw_object_list` | 214 |  |  |
| `0x1442c` | `draw_checkpoint_anim` | 118 |  |  |
| `0x15016` | `draw_result_row` | 86 |  |  |
| `0x1506c` | `draw_result_col` | 56 |  |  |
| `0x150a4` | `draw_dashboard` | 230 |  |  |
| `0x1518a` | `draw_fg_sprite` | 108 |  |  |
| `0x151f6` | `draw_buggy_wheels` | 182 |  |  |
| `0x152ac` | `draw_buggy` | 334 |  |  |
| `0x153fa` | `draw_buggy_lo` | 204 |  |  |
| `0x154c6` | `draw_buggy_hi` | 152 |  |  |
| `0x1555e` | `draw_hud` | 684 |  |  |
| `0x1580a` | `add_score` | 104 | ✅ verified | 2000-seed fuzz + edge cases |
| `0x15872` | `draw_crash_fx` | 392 |  |  |
| `0x159fa` | `draw_text` | 2 |  |  |
| `0x159fc` | `draw_text_row` | 12 |  |  |
| `0x15a08` | `draw_hud_gauge0` | 28 |  |  |
| `0x15a24` | `draw_hud_bar` | 96 |  |  |
| `0x15a84` | `draw_num_thunk` | 2 |  |  |
| `0x15a86` | `draw_num` | 112 |  |  |
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

## Verification notes (known gaps)

Surfaced by the high-effort code review; the harness itself was hardened (truncation now
raises; a stray write in the guard band fails loudly). Remaining, low-severity, deferred:

- **Blit return register (D0)** — only `Ln` verifies its status word. `Lf`/`Rf` and the four
  `*2` road-walk variants check pixels only; their D0 is settled when `draw_object` is ported.
- **Road-walk regime coverage** — the `*2` fuzz keeps x in the straddling-edge regime; the
  off-edge / full-fill / past-width branches of `row_left`/`row_right` are covered via the
  non-walk variants, not through the road walk itself.
- **fill_span/fill_rect flip slot** — fuzz pins `flip_idx=0`; the slot-4 buffer pointer is
  exercised by `clear_screen`/`fill_screen` but not by span/rect.
- **`_start` past `bsr main`** — verified only up to the checkpoint at 0x100d4 (its GEM init).
  The terminal Pterm and `appl_exit` after main are unreached (main never returns).
- **snd_voice command 0x88 ("end tune")** — this command rewrites the return address on the stack
  to re-enter REFRESH (`0x1b0f0`) after a TURNOFF, so it cannot be verified by a run-to-rts diff.
  Its memory effect (the TURNOFF) is reconstructed, but the fuzz excludes it (streams are built
  from the 12 other commands + notes). The remaining 12 commands and all pitch/note/glide paths
  are covered. The stepper also assumes D0's high byte is 0 (a design invariant: it indexes a
  256-entry byte table and a 13-entry jump table — a nonzero high byte runs off both).

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
(`snd_cmd_handler`/`snd_stub`). The only sound code left is the VBL orchestrator **`REFRESH`**
(`0x1b086`, not one of the 91 tracked functions): it drives the three voices then writes the
YM2149 PSG at `$ffff8800/8802`, which is outside the image, so verifying it needs a PSG-write
model in the harness (like the OS trap layer). Remaining beyond that: the gameplay/draw/HUD
families and the big orchestrators (`game_update`, `render_road`, `draw_hud`).
