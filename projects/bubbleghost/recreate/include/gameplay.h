/* gameplay.h — the castle, its objects, the ghost and the bubble.
 *
 * This subsystem is the in-room simulation: the room grid the castle is laid out on, the four
 * data tables that describe a room, and the per-frame update that turns the mouse and the shift
 * keys into a ghost, a puff of air and a drifting bubble (`../notes/gameplay.md` is the design
 * doc every field below was read against). The DRAWING is not here — the raw copies are
 * `include/blit.h`'s and the sprite work goes through the VDI — and neither is the sound: this
 * subsystem calls `include/sound.h`'s trigger API and owns none of it.
 *
 * THIS SUBSYSTEM OWNS THE WORLD. `A_room_table`, `A_object_table`, `A_candle_table`,
 * `A_probe_table`, `A_room_grid`, `A_room_number` and the ghost/bubble/drift/score globals live
 * here; another subsystem that needs one includes this header to READ it (README.md, "Adding a
 * function"). Three of them — `A_room_number`, `A_object_table`, `A_room_table` — and the
 * `OBJECT_*` / `ROOM_*` record offsets arrived here FROM `include/blit.h`, which held them on loan
 * while this subsystem was unported; STATUS.md's "Borrowed globals" predicted that move and its
 * rows are gone.
 *
 * THE RECORD BLOCKS BELOW ARE FROZEN (docs/agent-playbook.md §11). Several agents port routines
 * against them at once, so nobody adds a field: the offset a routine needs is already named. Every
 * line carries its PROVENANCE — the instruction the displacement was read off, and the case that
 * pins it — and the only permitted edit is upgrading `unpinned` to a test name in the same change
 * that ports the routine which pins it.
 */
#ifndef BG_GAMEPLAY_H
#define BG_GAMEPLAY_H

#include <stdint.h>

#include "clib.h"   /* CallerAddressRegisters: the A1/A2 a Setcolor's trampoline files */

/* ================================================================================================
 * The castle
 * ============================================================================================= */

#define ROOM_COUNT              36u     /* = ROOM_GRID_ROWS x ROOM_GRID_COLS; every table below is
                                         * indexed by room_number. No instruction names it — the
                                         * walk's bounds are the grid's — so it is pinned by DATA:
                                         * test_blit.py::test_objects_animate_and_draw_shipped_rooms
                                         * drives all 36 records of `object_table` */

/* ---- room_grid @ 0x2328e — 6 rows x 6 words ---------------------------------------------------
 * `room_number = room_grid[grid_row][grid_col]`, a boustrophedon walk of 0..35 (../notes/
 * gameplay.md §4). A new game starts at (5, 4) = room 1. */
#define ROOM_GRID_ROWS          6u      /* names.txt, room_grid: 36 words / ROOM_GRID_COLS */
#define ROOM_GRID_COLS          6u      /* = ROOM_GRID_ROW_BYTES / 2, the column being a word:
                                         * `asl.l #1,d0` @ 0x10736 scales grid_col */
#define ROOM_GRID_ROW_BYTES     12u     /* `muls.w #$c,d1` @ 0x105ee on grid_row, and again at
                                         * 0x106fe and 0x1072c; names.txt, room_grid */

/* ---- room_table @ 0x21a4a — 36 records of 0x78 bytes ------------------------------------------
 * A record opens with the 5 x 10 word tile map, then four (x, y) entry points in TILE units, then
 * the room's ambient sound. PROVENANCE: each offset is a displacement read off one named
 * instruction; the map three were `include/blit.h`'s and moved here with `A_room_table`. */
#define ROOM_STRIDE             120u    /* `muls.w #$78` @ 0x13a40; pinned by
                                         * test_blit.py's draw_room_to_stage cases */
#define ROOM_MAP_ROW_BYTES      20u     /* `muls.w #$14` @ 0x13a4a = ROOM_TILE_COLS words; pinned by
                                         * the same cases and by test_gameplay.py's candle patch */
#define ROOM_MAP_CELL_BYTES     2u      /* `asl.l #1,d0` @ 0x13a58: a map cell is a word */
/* The four entry points, read off `lea -13420(a4)` @ 0x1286e (= room_table + 0x64), the
 * `add.w d1,d0` on entry_dir*2 + `asl.l #1` @ 0x12874 that indexes them, and the `move.w #$1,d0`
 * @ 0x12884 that reaches the pair's second word. names.txt, UNPINNED: the only routine that steps
 * by them is `game_frame_update`'s respawn, inside the unported death sequence. */
#define ROOM_ENTRY_POINTS       0x64u   /* `lea -13420(a4)` @ 0x1286e = room_table + 0x64 */
#define ROOM_ENTRY_STRIDE       4u      /* `muls.w #$2,d0` @ 0x12862 on entry_dir then `asl.l #1`
                                         * @ 0x12874: the index steps four bytes per direction */
#define ROOM_ENTRY_X            0u      /* the pair's first word, which that index reaches */
#define ROOM_ENTRY_Y            2u      /* `move.w #$1,d0 / add.w d1,d0` @ 0x12884 with d1 =
                                         * entry_dir*2, then the same `asl.l #1`: +2 */
#define ROOM_CANDLE_SFX         0x74u   /* `lea -13404(a4)` @ 0x12dde = room_table + 0x74; word,
                                         * -1 = no candle. Pinned by test_gameplay.py's
                                         * test_ghost_blow_extinguishes_a_candle */

/* ---- object_table @ 0x2069a — 36 rooms x 10 slots x 14 bytes ----------------------------------
 * The room's animated furniture. Slots are drawn after the room is presented, so an object is part
 * of the background the collision probe reads. PROVENANCE: the Alcyon compiler reaches each field
 * through its OWN `lea -n(a4),a0`, and `A_object_table` is `A4_BASE - 18560`, so the displacement
 * NAMES the offset: -18560 is field 0, -18558 is field 2, and so on. */
#define OBJECT_SLOTS            10u     /* `cmpi.w #$a` @ 0x1394c */
#define OBJECT_STRIDE           14u     /* `muls.w #$e` @ 0x13790 */
#define OBJECT_ROOM_STRIDE      140u    /* `muls.w #$8c` @ 0x13786 = OBJECT_SLOTS x OBJECT_STRIDE */
/* word: base GHOST.DAT tile; negative = empty slot. `lea -18560(a4)` @ 0x1378a; pinned by
 * test_blit.py::test_objects_animate_and_draw_word_edge_branches */
#define OBJECT_TILE             0u
/* word: frames left; the frame steps when it is already 0. `lea -18558(a4)` @ 0x137ac; pinned by
 * test_blit.py::test_objects_animate_and_draw_countdown_reaches_zero_and_reloads */
#define OBJECT_COUNTDOWN        2u
/* word: what COUNTDOWN is reloaded with. `lea -18556(a4)` @ 0x137d2; pinned by the same case */
#define OBJECT_RELOAD           4u
/* word: tile column 0..9. `lea -18554(a4)` @ 0x12d54; pinned by
 * test_gameplay.py::test_ghost_blow_extinguishes_a_candle, which reads it back as a map column */
#define OBJECT_X                6u
/* word: tile row 0..4. `lea -18552(a4)` @ 0x12d88; pinned by the same case */
#define OBJECT_Y                8u
/* word: animation frame; the tile drawn is TILE + FRAME. `lea -18550(a4)` @ 0x1380a; pinned by
 * test_blit.py::test_objects_animate_and_draw_shipped_rooms */
#define OBJECT_FRAME            10u
/* word: FRAME wraps to 0 when it reaches this minus one. `lea -18548(a4)` @ 0x13828; pinned by
 * test_blit.py::test_objects_animate_and_draw_countdown_reaches_zero_and_reloads */
#define OBJECT_FRAME_COUNT      12u

/* The ONE object type with hard-coded behaviour, and it is hard-coded to two slots
 * (../notes/gameplay.md §5): a fan pushes the bubble left over a band to its left. */
#define OBJECT_FAN_TILE         220u    /* `cmpi.w #$dc,(a0)` @ 0x125f4 and @ 0x12672 */
#define OBJECT_FAN_SLOT_A       3u      /* `lea -18518(a4)` @ 0x125ee = slot 3's TILE */
#define OBJECT_FAN_SLOT_B       4u      /* `lea -18504(a4)` @ 0x1266c = slot 4's TILE */

/* ---- candle_table @ 0x22b2a — 36 rooms x 6 words ----------------------------------------------
 * The one scripted interaction in the game. PROVENANCE: `lea -9200(a4)` @ 0x12d2e is word 0 and
 * `A_candle_table` is `A4_BASE - 9200`, so each displacement below names its own offset; all six
 * are pinned by test_gameplay.py::test_ghost_blow_extinguishes_a_candle, which drives the script. */
#define CANDLE_STRIDE           12u     /* `muls.w #$c` @ 0x12d2a */
#define CANDLE_FLAME_SLOT_A     0u      /* `lea -9200(a4)` @ 0x12d2e, the record's word 0: the
                                         * object slot of lit-flame part A; -1 = no candle here */
#define CANDLE_FLAME_SLOT_B     2u      /* `lea -9198(a4)` @ 0x12e7c: part B */
#define CANDLE_TILE_A           4u      /* `lea -9196(a4)` @ 0x12e2e: tile to put in DEST_A */
#define CANDLE_DEST_A           6u      /* `lea -9194(a4)` @ 0x12ea6: which slot receives it */
#define CANDLE_TILE_B           8u      /* `lea -9192(a4)` @ 0x12e40 */
#define CANDLE_DEST_B           10u     /* `lea -9190(a4)` @ 0x12ed0 */
#define CANDLE_NONE             (-1)    /* `cmpi.w #$ffff,(a0)` @ 0x12d34 */

/* ---- probe_table @ 0x1f14a — 6 phases x 8 (dx, dy) word pairs ---------------------------------
 * The whole hazard model is eight pixel reads off the composed screen (../notes/gameplay.md §6).
 * PROVENANCE: `lea -24016(a4)` @ 0x1303c is phase 0's first dx and `A_probe_table` is
 * `A4_BASE - 24016`; the eight probes are the eight `lea`s four bytes apart between there and
 * `lea -23986(a4)` @ 0x131ce. All pinned by test_gameplay.py's collision cases. */
#define PROBE_PHASES            6u      /* `cmpi.w #$5` @ 0x13010: the phase wraps after 5 */
#define PROBE_PHASE_STRIDE      0x20u   /* `muls.w #$20` @ 0x13022 = PROBES x PROBE_STRIDE */
#define PROBES                  8u      /* the eight inlined pairs: `lea -24014(a4)` @ 0x13026
                                         * through `lea -23990(a4)` @ 0x13180 */
#define PROBE_STRIDE            4u      /* consecutive pairs' `lea`s are four bytes apart:
                                         * -24016/-24014, -24012/-24010, ... -23992/-23990 */
#define PROBE_DX                0u      /* `lea -24016(a4)` @ 0x1303c, added to `bubble_x` */
#define PROBE_DY                2u      /* `lea -24014(a4)` @ 0x13026, added to `bubble_y` — pushed
                                         * FIRST, since the C call pushes right to left */

/* ---- the 58-word world block ------------------------------------------------------------------
 * Every table cell a blown-out candle mutates, over the ten candle rooms, saved and restored per
 * player around a turn swap (../notes/gameplay.md §9). `reset_world_state` writes the lit-candle
 * defaults to the live tables AND to both blocks in one pass. PROVENANCE: the 58 entries are the
 * 58 `move.w -n(a4),-m(a4)` pairs of `save_world_p1` @ 0x13ff4, read in order; `src/gameplay.c`'s
 * `WORLD_CELLS` is that list and its own comment says which table cell each one is. */
#define WORLD_BLOCK_WORDS       58u     /* the 174 stores of `reset_world_state` @ 0x10f20, / 3 */
#define WORLD_BLOCK_CELL_BYTES  2u      /* the destination displacements of `save_world_p1` @
                                         * 0x13ff4 step by two: -7310, -7312, -7314, ... */

/* ================================================================================================
 * The ghost, the blow and the bubble
 * ============================================================================================= */

/* The eight facings the mouse buttons step through, and the tile each one selects. */
#define GHOST_FACINGS           8u      /* `cmpi.w #$7` @ 0x12572 / `bge` on 0 @ 0x125b4 */
#define GHOST_TILES_PER_FACING  5u      /* `muls.w #$5` @ 0x12582: tile = facing*5 + anim */
#define GHOST_IDLE_ANIM_LAST    2u      /* `cmpi.w #$2,d0` @ 0x1252e — the IMMEDIATE, not the cycle
                                         * length: the step wraps on the value it arrived with, so
                                         * the idle walk runs 0, 1, 2, 3 and 3 wraps to 0 */
#define GHOST_BLOW_ANIM         4u      /* `move.w #$4,-7990(a4)` @ 0x124b2: pinned while blowing */

/* The air gauge. It starts full, drains one unit per blowing frame and refills three per idle one,
 * so a full breath is ~35 frames of blow and ~12 of recovery. */
#define BREATH_MAX              35u     /* `cmpi.w #$23` @ 0x1253c */
#define BREATH_REFILL_PER_FRAME 3u      /* `addq.w #3` @ 0x12538 */

/* The shift-key mask `vq_key_s` answers with. Blowing is on while the state is NEITHER of these —
 * i.e. any modifier except Ctrl alone (../notes/gameplay.md §3). */
#define KEY_SHIFT_NONE          0u      /* `move.w -7684(a4),d0 / beq` @ 0x124a4 */
#define KEY_SHIFT_CTRL_ONLY     4u      /* `cmpi.w #$4,-7684(a4)` @ 0x124aa */

/* The ghost's colour while it is idle, and the colour the frame its breath runs out. Both go to
 * XBIOS `Setcolor(15, …)`, which the model no-ops — so the differential CANNOT see either
 * (STATUS.md's residual for this subsystem). */
#define GHOST_PEN               15u     /* `move.w #$f,-(a7)` @ 0x124f6 and @ 0x1254e */
#define GHOST_COLOUR_IDLE       0x777u  /* @ 0x1254a */
#define GHOST_COLOUR_SPENT      0x733u  /* @ 0x124f2 */

/* The bubble's nine animation frames live at sprite indices 4..12 and wrap back to 4. */
#define BUBBLE_FIRST_FRAME      4u      /* `move.w #$4,-7986(a4)` @ 0x12334 */
#define BUBBLE_LAST_FRAME       11u     /* `cmpi.w #$b,d0 / ble` @ 0x1232e: 12 wraps to 4 */
#define BUBBLE_POPPED_FRAME     0u      /* `clr.w -7986(a4)` @ 0x131e8 — and what the alive test
                                         * at 0x126ec reads back */

/* The blow test's gate and its eight direction cones (../notes/gameplay.md §3, "Blowing"). The
 * four diagonal multipliers really are asymmetric — 4/3/3/4 — and that is in the image. */
#define BLOW_RANGE              50      /* `cmpi.w #$32` @ 0x12a26 and @ 0x12a42, on |dx| and |dy| */
#define BLOW_CONE_LIMIT         40      /* `cmpi.w #$28` / `cmpi.w #$ffd8` around each cone sum */
#define BLOW_SPEED_ORTHOGONAL   300     /* `move.w #$12c` @ 0x12a78 and its three siblings */
#define BLOW_SPEED_DIAGONAL     250     /* `move.w #$fa` @ 0x12bb8 and its three siblings */

/* The candle-extinguish window: the candle 13..44 px to the ghost's LEFT and 4..19 px below it,
 * with the ghost facing left. The bounds are exclusive on both sides, as the `bge`/`ble` pairs are. */
#define CANDLE_FACING_INDEX     1       /* `cmpi.w #$1,-8018(a4)` @ 0x12da4: blow_facing_plus1 for
                                         * facing 0 (left) */
/* The two horizontal bounds are spelt as MAGNITUDES and negated where they are used: the value a
 * header names has to be readable by `test/test_constants.py`'s scraper, which takes an unsigned
 * literal and not a parenthesised negative — and a bound the battery restates but cannot pin is a
 * bound that drifts silently (README.md, "Adding a function"). */
#define CANDLE_DX_NEAR          12u     /* `cmpi.w #$fff4` @ 0x12dae: delta_x must be < -this */
#define CANDLE_DX_FAR           45u     /* `cmpi.w #$ffd3` @ 0x12db8: ...and > -this */
#define CANDLE_DY_MAX           20      /* `cmpi.w #$14` @ 0x12dc2 */
#define CANDLE_DY_MIN           3       /* `cmpi.w #$3` @ 0x12dcc */
#define CANDLE_SCORE            5000    /* `addi.l #$1388,-8042(a4)` @ 0x12fe0 */

/* The drift pulse. A blow arms a direction and a speed; the speed is applied for ONE frame every
 * `drift_pulse` frames and decays, so the bubble coasts and stalls (../notes/gameplay.md §3). */
#define DRIFT_SPEED_DECAY       50      /* `subi.w #$32,-8014(a4)` @ 0x1297c */
#define DRIFT_SPEED_FLOOR       100     /* `cmpi.w #$64` @ 0x12982 */
#define DRIFT_INTERVAL_MAX      200     /* `cmpi.w #$c8` @ 0x12994 */
#define DRIFT_INTERVAL_DIVISOR  10      /* `divs.w #$a` @ 0x129a8: pulse = interval / 10 */
#define DRIFT_VELOCITY_SCALE    100     /* `divs.w #$64` @ 0x1271e: velocity is applied as /100 px */

/* The fan's push region and the impulse it applies, both hard-coded (../notes/gameplay.md §5). */
#define FAN_DX_MIN              5       /* `cmpi.w #$5` @ 0x12632 */
#define FAN_DX_MAX              60      /* `cmpi.w #$3c` @ 0x1263a */
#define FAN_DY_LIMIT            15u     /* `cmpi.w #$fff1` @ 0x12642 and `cmpi.w #$f` @ 0x1264a:
                                         * |delta_y| < this, the band being symmetric — unlike the
                                         * horizontal one, which is 5..60 */
#define FAN_PUSH_PIXELS         2u      /* `move.w #$fffe,-8020(a4)` @ 0x12658: `x_impulse` is set
                                         * to MINUS this — a fan only ever pushes left */

/* The bubble spawns on a TILE corner: the entry point's (x, y) times the tile size. */
#define ENTRY_POINT_PIXELS      32      /* `muls.w #$20` @ 0x1287c and @ 0x128a8 */

/* ================================================================================================
 * The screen probe
 * ============================================================================================= */

/* `get_pixel` @ 0x13bea assembles a colour index out of the four plane words of one 16-pixel cell.
 * It reads the WORK buffer directly — no clipping, no bounds test — which is what `make guarded`
 * is run for on this battery. */
#define PIXELS_PER_WORD         16      /* `divs.w #$10` @ 0x13bf8 and `muls.w #$10` @ 0x13c26 */
#define PLANE_WORD_BYTES        8       /* `muls.w #$8` @ 0x13c14: four planes of one word */
#define PIXEL_MSB               15      /* `move.w #$f,d6 / sub.w` @ 0x13c30: bit 15 is the LEFTMOST
                                         * pixel of a plane word */

/* ================================================================================================
 * The HUD
 * ============================================================================================= */

/* `hud_draw_counters` @ 0x113d2 and the two bonus-bar routines are NOT reconstructed — they reach
 * the front end's VDI binding, which owns the parameter block (STATUS.md, "Not reconstructed") —
 * so their geometry is not named here. `itoa_padded`, which every counter is formatted through,
 * is; these two are its whole arithmetic. */
#define DECIMAL_RADIX           10u     /* `move.l #$a,d0` @ 0x114fc: itoa_padded's divisor */
#define ASCII_ZERO              0x30u   /* `add.l #$30,d0` @ 0x1150c */

/* ================================================================================================
 * Globals this subsystem owns
 * ============================================================================================= */

/* --- the tables --- */
#define A_probe_table           0x1f14au  /* PROBE_PHASES x PROBE_PHASE_STRIDE */
#define A_object_table          0x2069au  /* ROOM_COUNT x OBJECT_ROOM_STRIDE */
#define A_room_table            0x21a4au  /* ROOM_COUNT x ROOM_STRIDE */
#define A_candle_table          0x22b2au  /* ROOM_COUNT x CANDLE_STRIDE */
#define A_room_grid             0x2328eu  /* ROOM_GRID_ROWS x ROOM_GRID_ROW_BYTES */

/* --- room and progress --- */
#define A_deaths_in_room        0x22f62u  /* word: subtracts 500 each from the room bonus */
#define A_max_room_reached      0x22f74u  /* word: starts at 1 */
#define A_level_complete        0x22fbeu  /* word: set when room 35 and bubble_x > 195 */
#define A_room_number           0x23120u  /* word: 0..35 = room_grid[grid_row][grid_col] */
#define A_in_room               0x23150u  /* word: the room loop runs while != 0 */
#define A_entry_dir             0x23152u  /* word: 0 left, 1 bottom, 2 right, 3 top */
#define A_grid_row              0x23154u
#define A_grid_col              0x23156u

/* --- the ghost --- */
#define A_seq_counter           0x22fe2u  /* word: death anim / ending walk / sfx reload scratch */
#define A_btn_right_ready       0x22fc2u  /* BYTE: edge latch for mouse button 2 */
#define A_btn_left_ready        0x22fc4u  /* BYTE: edge latch for mouse button 1 */
#define A_blow_facing_plus1     0x22fc8u  /* word: (ghost_tile + 1) / 5 */
#define A_breath                0x22fcau  /* word: the air gauge, 0..BREATH_MAX */
#define A_ghost_anim            0x22fe4u  /* word */
#define A_ghost_facing          0x22fe6u  /* word: 0..7 */
#define A_ghost_tile            0x22feau  /* word: facing*5 + anim */
#define A_ghost_y               0x22ff0u  /* word: pixels */
#define A_ghost_x               0x22ff2u  /* word: pixels */

/* --- the bubble --- */
#define A_x_impulse             0x22fc6u  /* word: one-frame additive push; only the fan writes it */
#define A_drift_speed           0x22fccu  /* word */
#define A_drift_pulse           0x22fceu  /* word: frames until the next pulse */
#define A_drift_interval        0x22fd0u  /* word: 0..DRIFT_INTERVAL_MAX */
#define A_delta_y               0x22fd2u  /* word: scratch, target_y - reference_y */
#define A_delta_x               0x22fd4u  /* word: scratch */
#define A_drift_dir_y           0x22fd6u  /* word: -1 / 0 / +1 */
#define A_drift_dir_x           0x22fd8u  /* word */
#define A_drift_vel_y           0x22fdau  /* word: applied as /DRIFT_VELOCITY_SCALE px */
#define A_drift_vel_x           0x22fdcu  /* word */
#define A_probe_phase           0x22fdeu  /* word: 0..5 */
#define A_bubble_alive          0x22fe0u  /* word */
#define A_bubble_frame          0x22fe8u  /* word: 0 = popped, else 4..12 */
#define A_bubble_y              0x22fecu  /* word: pixels */
#define A_bubble_x              0x22feeu  /* word: pixels */

/* --- HUD and score --- */
#define A_bonus_tick            0x22f76u  /* word: the bar's 3-frame divider */
#define A_lives                 0x22fa8u  /* LONG: 5 per turn, and the turn ends at -1 */
#define A_hi_score              0x22facu  /* LONG */
#define A_score                 0x22fb0u  /* LONG */
#define A_bonus_bar             0x22fb4u  /* word: the bar's right end, 318 down to a floor of 35 */

/* --- the two players: the world block each turn is saved into (../notes/gameplay.md §9) ------
 * The rest of the per-player context (score, lives, grid position) is written by the death
 * sequence and by `game_top_loop`, neither of which is ported; those addresses are not named here
 * because nothing in this subsystem reaches them yet. */
#define A_p2_world_block        0x231a6u  /* WORLD_BLOCK_WORDS words */
#define A_p1_world_block        0x2321au

/* --- the sound-on flag, which this subsystem OWNS -----------------------------------------------
 * It used to be on loan from the front end. It is not: the routine that WRITES it is
 * `game_frame_update`'s `^S` arm @ 0x123ea, which is this file's, and every sfx trigger here scales
 * its volume index by it. `title_menu_loop` @ 0x115d6 reads it too — a reader in another subsystem
 * is not ownership, and that one includes this header when it is ported. */
#define A_sound_enabled         0x2315eu  /* word: 0 = silent, 1 = on */

/* The input block `vq_mouse` / `vq_key_s` / the `Crawio(0xff)` poll fill is the FRONT END'S, and is
 * defined in `include/frontend.h`; `src/gameplay.c` includes that header to read it. (`A_key_raw`
 * is written from here, at 0x1238e, but it is one word of that block and the block has one owner.)
 * This is a finished migration, so there is no row for it in ../STATUS.md's "Borrowed globals". */

/* The three doubles the mouse scaling divides by. They are DATA, not bss — `a4 + n` rather than
 * `a4 - n` — and the game reaches them through the software float package (`include/clib.h`). */
#define A_const_mouse_x_scale_room35 0x25182u  /* `pea 616(a4)` @ 0x12446: 1.684 */
#define A_const_mouse_x_scale        0x2518au  /* `pea 624(a4)` @ 0x1246a: 1.115 */
#define A_const_mouse_y_scale        0x25192u  /* `pea 632(a4)` @ 0x1248c: 1.577 */

#define ROOM_WIDE                    35        /* `cmpi.w #$23,-7674(a4)` @ 0x12434: the one room
                                                * whose mouse scaling differs */
#define FP_OP_DIVIDE                 0x803u    /* `move.w #$803,-(a7)` @ 0x1244e, 0x12472 and
                                                * 0x12494: the opcode all three divides carry */

/* ================================================================================================
 * Cores
 * ============================================================================================= */

int16_t get_pixel(const uint8_t *image, int16_t x, int16_t y);
void    bubble_collision_probe(uint8_t *image);
void    reset_world_state(uint8_t *image);
void    save_world(uint8_t *image, uint32_t block);
void    restore_world(uint8_t *image, uint32_t block);
void    itoa_padded(uint8_t *image, int32_t value, uint32_t buffer, int16_t width);
void    ghost_blow_body(uint8_t *image);

/* The seven slices of `game_frame_update` @ 0x12322, in the order it runs them. Each is entered at
 * its own PC by the battery and diffed at the next one's, so the region each covers is exactly what
 * the differential proves; the two gaps — the front-end poll and the death sequence — are named in
 * `src/gameplay.c`'s header comment and in STATUS.md. */
void    frame_advance_bubble_frame(uint8_t *image);
void    frame_scale_mouse_to_ghost(uint8_t *image);
void    frame_blow_or_recover(uint8_t *image, CallerAddressRegisters saved);
void    frame_step_facing(uint8_t *image);
void    frame_apply_fans(uint8_t *image);
int16_t frame_step_live_bubble(uint8_t *image);
void    frame_drift_pulse(uint8_t *image);

#endif /* BG_GAMEPLAY_H */
