# Reconstruction status — BuggyBoy

Human-readable C reconstruction of all 91 functions, each **verified byte-for-byte
against the original 68000 code** by the differential harness (Musashi oracle vs the
compiled reconstruction). See [`README.md`](README.md) for how it works.

**Verified: 18/91.**

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
| `0x10000` | `_start` | 220 |  |  |
| `0x100dc` | `gem_aes` | 14 |  |  |
| `0x100ea` | `gem_vdi` | 12 |  |  |
| `0x10100` | `main` | 494 |  |  |
| `0x102ee` | `wait_vbl_set_offset` | 18 |  |  |
| `0x10300` | `set_screen_offset` | 38 |  |  |
| `0x10326` | `blit_road_scroll` | 340 |  |  |
| `0x1047a` | `init_scoretable` | 62 |  |  |
| `0x104b8` | `init_leg` | 360 |  |  |
| `0x10620` | `unpack_graphics` | 364 |  |  |
| `0x1078c` | `build_sprite_shifts` | 102 |  |  |
| `0x107f2` | `build_sprite_shifts_msk` | 140 |  |  |
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
| `0x11ba4` | `evt_flag_gate` | 104 |  |  |
| `0x11c2c` | `evt_collision` | 46 |  |  |
| `0x11c5a` | `evt_score_msg` | 24 |  |  |
| `0x11c7a` | `play_event_tune` | 56 |  |  |
| `0x11cb2` | `handle_marker` | 42 |  |  |
| `0x11f4c` | `build_road_geometry` | 356 | ✅ verified | 300-seed fuzz (whole-image) |
| `0x120b0` | `read_input` | 70 |  |  |
| `0x120f8` | `set_rez` | 24 | ✅ verified | trap layer (Ikbdws); D0.b -> config byte |
| `0x12110` | `read_joystick` | 20 |  |  |
| `0x12124` | `install_handlers` | 50 |  |  |
| `0x12166` | `load_graphics` | 146 |  |  |
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
| `0x1b252` | `EGOFF` | 16 |  |  |
| `0x1b268` | `TURNOFF` | 20 |  |  |
| `0x1b2e8` | `snd_voice_a` | 4 |  |  |
| `0x1b2ec` | `snd_voice_b` | 160 |  |  |
| `0x1b3ba` | `snd_stub` | 4 |  |  |
| `0x1b3be` | `snd_cmd_handler` | 244 |  |  |
| `0x1b560` | `INITFX` | 60 |  |  |
| `0x1b59c` | `INITTUNE` | 86 |  |  |

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

## OS trap layer

OS-bound functions now run under the oracle: `trap #1/#13/#14/#2` are serviced by a
deterministic model (`include/os.h`, dispatched in `oracle/shim.c`). Calls that only touch
hardware/files (Setpalette/Setcolor/Setscreen, sound, console, Ikbdws) have no image effect;
Physbase/Logbase → OS_SCREEN_BASE, Malloc bump-allocates, Fopen → a fixed handle; XBIOS
Supexec runs the passed routine in place. Anything not faithfully modeled (**Fread**,
GEMDOS **Super**, all **GEM/AES/VDI via trap #2**, unknown fn) is counted and `emu.run`
**raises** — a function that hits one cannot be falsely "verified".

Unlocked next (need model extensions): Fread → a file model; GEM trap #2 → AES/VDI
param-block modeling (required for `_start`/`main`). Functions that Malloc large screen
buffers also need a larger `IMAGE_SIZE`.
