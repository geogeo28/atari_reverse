/* addrs.h — named Ghidra addresses for BUGGYBOY.PRG globals (load base 0x10000).
 *
 * Source of truth is projects/buggyboy/names.txt; these mirror the `var` lines for
 * the globals the reconstruction touches. Add entries as functions are ported.
 */
#ifndef BB_ADDRS_H
#define BB_ADDRS_H

/* ---- score / event state ---- */
#define A_score_bcd       0x1824c   /* first 4 of 6 ASCII score digits (MS first) */
#define A_score_counter   0x18250   /* last 2 ASCII score digits (contiguous w/ score_bcd) */
#define A_score_str       0x18230   /* HUD score string; live digits at [4..9] */

/* ---- crash / game-over HUD effect (draw_crash_fx @ 0x15872) ---- */
#define A_crash_active    0x18c7a   /* gate: 0 -> set abort_flag and bail */
#define A_abort_flag      0x18c4e   /* game-over abort countdown (0xffff / 0x33, decays by 2) */
#define A_crash_frame     0x18c78   /* crash-effect frame counter (drives the colour cycle) */
#define A_time_left       0x18cfc   /* bonus time remaining; drained by the crash effect */
#define A_crash_lap       0x18c4a   /* remaining bonus units (rendered as a digit) # ctx */
#define A_crash_bars      0x18d00   /* number of gauge bars to draw (0-5) # ctx */
#define A_crash_bar_yoff  0x18c76   /* gauge-bar vertical offset (0 active, 0x18 idle) # ctx */

/* ---- HUD renderer (draw_hud @ 0x1555e) ---- */
#define A_hud_speed_txt    0x1823c  /* HUD speedometer string: prefix word ("/N") + 2 digits */
#define A_hud_time_txt     0x18246  /* HUD time string; leading-blank 2 digits at +1, +2 */
#define A_dsp_toggle       0x18c7c  /* nonzero suppresses the dashboard-variant sprite blit */
#define A_dsp_variant_idx  0x18c7e  /* byte offset into the dashboard-variant sprite record table */
#define A_dsp_color_scroll 0x18d06  /* offset added to the colour-bar colour-index cursor */
#define A_gauge_blink      0x18d02  /* small-gauge blink phase (decrements; bit1 gates the draw) */
#define A_gauge_blink_on   0x18d04  /* nonzero enables the small-gauge bar under the blink */
#define A_hud_crash_timer  0x18c4c  /* crash-fx arm timer: <0 runs draw_crash_fx, >0 decays by 2 */

/* ---- high-score / results screen (update_highscore @ 0x1238e) ---- */
#define A_countdown_timer 0x18262   /* name-entry countdown value (starts 30); rendered as "TIME nn" */
#define A_countdown_sub   0x18264   /* per-frame sub-counter; decrements countdown_timer every 0x11 frames */
#define A_highscore_table 0x18266   /* per-leg high-score rows: 9 x 0xe bytes (6 score digits + name), stride 0x80 by leg */
#define HIGHSCORE_ROWS    9         /* rows per leg table */
#define HIGHSCORE_ROW     0xe       /* bytes per row */
#define HIGHSCORE_LEG_STRIDE 0x80   /* bytes per leg's table (leg_index << 7) */
#define A_default_scores  0x184e6   /* 9 x 2-digit default high scores "403938353025201510" */

/* ---- gameplay state ---- */
#define A_game_over_flag  0x18c34   /* tst.w'd at add_score entry */
#define A_leg_index       0x18c38   /* current leg (0-4); indexes result strings + palette */
#define A_obj_scan_off    0x18c58   /* word paired with view_flags; draw_object_list adds it to a5 */
/* draw_object_list @0x1306e display-list dispatcher bases (Ghidra addresses). */
#define A_obj_list_base   0x16c06   /* a5 base: per-row [dst_word, xoff_word] then 15 per-object x words */
#define A_obj_flags       0x18ebc   /* a3 base: per-object flag word (sign gates the special dispatch; low 6 bits = type) */
#define A_obj_xoff_tbl    0x18f26   /* a4 base: per-row shared x-offset word */
#define A_obj_type_jumptable 0x13144 /* word offsets (from this base) to the object-sprite handlers */
#define A_road_edge_sel   0x18c5a   /* signed word added to render_road's a6 edge-table base (0x15c3a) */
#define A_leg_flags_c90   0x18c90   /* per-leg state pair, init 0x00440002 by init_leg # ctx */
#define A_obj_markers     0x18d3c   /* 14 x 0x20-byte per-object marker records, seeded by init_leg */
/* ---- draw_game_objects @ 0x12ef6 per-frame state ---- */
#define A_marker_decay      0x18cf0   /* [0]=active word, [2]=record byte-offset, [4]=countdown word */
#define A_marker_decay_base 0x18d34   /* base of the 14 records the decay clears (stride 0x20) */
#define A_anim_counter      0x17f10   /* frame counter (+=2/frame); &0x1e indexes the anim tables */
#define A_anim_word_tbl     0x17ec8   /* word table indexed by (counter & 0x1e) -> anim_word */
#define A_anim_word         0x18c74   /* current anim word; mirrored to buf_a+0xd70 and buf_a+0x1250 */
#define A_anim_coloridx_tbl 0x17ee8   /* word table indexed by (counter & 0x1e); <<3 -> color_pairs offset */
#define A_anim_color        0x17f08   /* current 8-byte (2-long) colour pair copied from color_pairs */
#define A_sprite_list_base  0x18d5a   /* sprite-count loop base (== A_road_width_src); stride 0x20 */
#define A_obj_sprite_flags  0x18d5c   /* a3 base for the sprite-driven draw_object_list calls (list_base+2) */
#define A_obj_sprite_disp   0x16a90   /* a5 base for the sprite-driven draw_object_list calls */
#define OBJ_ANIM_IDX_MASK   0x1e      /* counter & this indexes the anim tables */
#define GOBJ_ANIM_BUF_OFF1  0xd70     /* buf_a + this = anim_word mirror 1 */
#define GOBJ_ANIM_BUF_OFF2  0x1250    /* buf_a + this = anim_word mirror 2 */
/* ---- input (read_input @ 0x120b0, check_abort @ 0x128ea) ---- */
#define A_input_prev      0x18c42   /* baseline input snapshot; check_abort aborts on a differing live input # ctx */
#define A_input_state     0x18c44   /* current input bits: fire 0x80, up 1, down 2, left 4, right 8 */
#define A_last_key        0x18c46   /* last keyboard scancode (read_input's fallback source) */
#define A_dash_marker     0x18c3a   /* dashboard progress-marker record (long); seeded per-leg by init_leg_dash, walked by game_update */
#define A_spin_state      0x18caa   /* buggy spin state; <0 while spinning after a crash */
#define A_anim_frame      0x18d0c   /* word byte-offset into fg_anim_tbl for the current frame */
#define A_wheel_pos       0x18cc0   /* buggy wheel/steer position; selects the body piece list */
#define A_buggy_variant   0x18cc6   /* buggy-hi lean piece-list variant index # ctx */
#define A_lean_state      0x18cc2   /* buggy lean state; >= 0x1e skips the hi overlay */
#define A_buggy_lean_x10  0x18cc4   /* lean_state * 10 (draw_buggy scratch) # ctx */
#define A_crash_disp      0x18c68   /* vertical crash displacement (scanline offset); shifts the buggy up */
#define A_buggy_pitch_off 0x18cbe   /* vertical buggy position offset (road pitch) # ctx */
#define A_buggy_skid_off  0x18cbc   /* horizontal buggy skid offset (+/-8) # ctx */
#define A_speed_raw       0x18cf8   /* raw speed; drives the lean-animation rate */
#define A_lean_accum      0x18d10   /* lean-anim rate accumulator (advances lean_frame at 8) # ctx */
#define A_lean_frame      0x18d12   /* lean-anim frame offset into the hi piece table (0,8,0x10) # ctx */
#define A_buggy_draw_flag 0x18d0e   /* nonzero enables the buggy-body draw # ctx */
#define A_buggy_gate      0x18eba   /* byte OR'd with fg_gate (0x18ebb); bit7 suppresses the body # ctx */
#define A_hiscore_pos     0x18c9c   /* 1-based rank the new score reaches in the leg's high-score table */
#define A_results_mode    0x18c9e   /* 0 = score made the table (name entry), 2 = did not; results layout */
#define A_setrez_mode     0x18be6   /* byte set_rez sends to the IKBD via XBIOS Ikbdws (0x19) */

/* ---- init_playfield @ 0x12af6 (leg-select / playfield-init loop) ---- */
#define A_idle_countdown  0x18c66   /* attract idle timer; reset to 0x15e on any input change, expiry -> intermission */
#define A_leg_dec_delay   0x18c62   /* leg-select auto-repeat delay: step to the previous leg (up/left) */
#define A_leg_inc_delay   0x18c64   /* leg-select auto-repeat delay: step to the next leg (down/right) */
#define A_leg_select_pal  0x17f62   /* leg-select screen palette (xbios_setpalette A0) */
#define A_leg_start_pal   0x17f82   /* palette flashed by the leg-start "get ready" animation */
#define A_leg_flash_tbl_a 0x17f12   /* word table, idx (anim_counter & 0xc) >> 1 */
#define A_leg_flash_tbl_b 0x17f1a   /* word table, idx (anim_counter & 0x1c) >> 1 */
#define A_leg_flash_tbl_c 0x17f2a   /* word table, idx (anim_counter & 0x1c) >> 1 */
#define A_leg_flash_tbl_d 0x17f3a   /* long table, idx (anim_counter & 6) */

/* ---- intermission @ 0x127a0 (attract-mode / between-legs loop) ---- */
#define A_leg_select      0x18c36   /* attract-mode leg selector (0-4); copied to leg_index each cycle */
#define A_int_frame_hi    0x18ca2   /* Phase-D per-leg dwell counter (word, 0..INT_D_DWELL-1) */
#define A_int_frame       0x18ca4   /* Phase-A scroll dwell counter (init 0x14) / Phase-C demo frame counter */
#define A_int_timer       0x18ca6   /* free-running Phase-A timer; gates the scroll advance at >= INT_SCROLL_GATE */
#define A_int_scroll      0x18ca8   /* vertical scroll position consumed by draw_intermission */

/* ---- screen / double-buffer ---- */
#define A_flip_idx        0x18bf2   /* word: 0 or 4, selects the draw buffer in physbase_tbl */
#define A_physbase_tbl    0x18bf4   /* table of screen-buffer pointers, indexed by flip_idx */

/* ---- GEM (AES/VDI) init (gem_aes @ 0x100dc, gem_vdi @ 0x100ea) ---- */
#define A_aes_pblk        0x19a40   /* AES pblk: {contrl,global,intin,intout,addrin,addrout} */
#define A_vdi_pblk        0x1a08c   /* VDI pblk: {contrl,intin,ptsin,intout,ptsout} */
#define A_aesvdi_contrl   0x19a58   /* contrl array (shared by AES + VDI); contrl[0] = opcode */
#define A_vdi_intin       0x19a8c   /* intin array (shared); v_opnvwk work_in */
#define A_vdi_ws_handle   0x19c8c   /* intout[0] (shared); graf_handle's physical handle lands here */
#define A_vdi_handle      0x1a0a0   /* the workstation handle _start keeps (copy of intout[0]) */

/* ---- IKBD vector install (install_handlers @ 0x12124) ---- */
#define A_kbdvbase        0x18bda   /* saved KBDVBASE pointer (Kbdvbase result), for the restore on exit */
#define A_mousevec_old    0x18bde   /* saved old KBDVBASE+0x10 (mousevec) vector */
#define A_joyvec_old      0x18be2   /* saved old KBDVBASE+0x18 (joyvec) vector */

/* ---- file loader (load_graphics @ 0x12166) ---- */
#define A_gfx_file_handle 0x18bea   /* GEMDOS handle temp (word), reused across the two opens */
#define A_mem_base        0x18bfc   /* COURSES.DAT read target (pointer into the big Malloc block) */
#define A_buf_aux         0x18bf8   /* aux buffer (mem_base+0x57000); unpack_graphics header stash */
#define A_buf_a           0x18c00   /* buffer a (mem_base+0x1900) */
#define A_buf_b           0x18c04   /* buffer b (mem_base+0xf660 == buf_c-0xd000); deinterleave scratch */
#define A_buf_c           0x18c08   /* GRAPHICS.GRA read target base; the file lands at +0xc350 */
#define A_fname_courses   0x17e1a   /* "COURSES.DAT" string in the image */
#define A_fname_graphics  0x17e2a   /* "GRAPHICS.GRA" string in the image */
#define GFX_LOAD_OFFSET   0xc350    /* GRAPHICS.GRA loads at buf_c + this */

/* ---- course-event engine (evt_* @ 0x11ba4.., handle_marker @ 0x11cb2) ---- */
#define A_flag_seq_count    0x18c48   /* current matched-in-a-row count */
#define A_flag_seq_off      0x18c40   /* word: byte offset into the expected-sequence table */
#define A_flag_seq_table    0x17e3a   /* const: expected roadside-object type sequence */
#define A_bonus_timer       0x18d08   /* frames left on the flag-gate bonus window */
#define A_collision_lock    0x18c84   /* nonzero suppresses the collision penalty */
#define A_engine_rpm        0x18c8c
#define A_speed             0x18cf6
#define A_obj_active        0x18eb4   /* per-object active flags; evt clears [d5+1] */
#define A_score_delta_bonus 0x17388   /* const BCD deltas passed to add_score */
#define A_score_delta_gate  0x17370
#define A_score_delta_msg   0x17376

/* ---- roadside-object blitter state (draw_object @ 0x1087e) ---- computed from road_width_tbl,
 * then fed (as registers) to the blit_obj_* variants. lx/rx = left/right edge x; *_off = scanline
 * dst offset; *_rows = rows-1. The _c_* set is the second (near-object) pass. */
#define A_obj_desc        0x18cd2   /* found road_width_tbl entry (long): flag bits + width */
#define A_obj_base_off    0x18cd6   /* base scanline dst offset ((0x59 - i/2) * 0xa0) */
#define A_obj_clear_w     0x18cd8   /* clear-fill longword count-1 for the scale2 top clear */
#define A_obj_center_rows 0x18cda   /* center-band fill rows-1 (-1 = no center band) */
#define A_obj_lx          0x18cdc   /* left edge x (max over the object's rows) */
#define A_obj_l_off       0x18cde   /* left blit scanline dst offset */
#define A_obj_l_rows      0x18ce0   /* left blit rows-1 */
#define A_obj_rx          0x18ce2   /* right edge x (min) */
#define A_obj_r_off       0x18ce4   /* right blit scanline dst offset */
#define A_obj_r_rows      0x18ce6   /* right blit rows-1 */
#define A_obj_c_lx        0x18ce8   /* near-pass left edge x */
#define A_obj_c_rx        0x18cea   /* near-pass right edge x */
#define A_obj_c_off       0x18cec   /* near-pass scanline dst offset */
#define A_obj_c_rows      0x18cee   /* near-pass rows-1 */
#define A_obj_shade       0x18c5e   /* sign selects the center-band / near fill pattern # ctx */

/* ---- sound driver (play_event_tune @ 0x11c7a; INITTUNE/INITFX/TURNOFF) ---- */
#define A_vbl_sound_vec   0x18c0c   /* VBL sound handler vector; set to REFRESH */
#define A_cur_tune_id     0x18cfa
#define A_refresh         0x1b086   /* REFRESH VBL handler address (stored into vbl_sound_vec) */
#define A_mzflag          0x1b07a   /* music-active flag */
#define A_fxflag          0x1b07b   /* effect-active flag */

/* ---- fill patterns ---- */
#define A_color_pairs     0x15afa   /* 8-byte (4-plane) solid-fill pattern per colour index */

/* ---- object-sprite blit engine view transform (helper 0x145fc) ---- */
#define A_obj_view_xform  0x1722a   /* per-view record table: [src-rewind word, packed a0/row word] */

/* ---- font / text (draw_text @ 0x159fa) ---- */
#define A_font_glyphs     0x176a8   /* 16-byte 1bpp glyphs, indexed char << 4 */
#define A_num_glyph_tbl   0x17c5e   /* per-digit word byte-offset into the pre-rendered num sprites */
#define A_probe_deltas    0x17e7a   /* 8 neighbor probes {delta_bit, delta_x} words; drives probe_collision */

/* ---- foreground / buggy sprites (draw_fg_sprite @ 0x1518a) ---- */
#define A_fg_anim_tbl     0x177a0   /* anim frames: [rows-1, dst_off, src_off(long, +buf_c)] x8 bytes */
#define A_spin_counter    0x18d0a   /* frames the buggy spins after a hard-curve crash */
#define A_spin_reset      0x18cc8   /* longword cleared when a spin starts # ctx */
#define A_sprite_suppress 0x18cd0   /* nonzero suppresses the foreground sprite draw # ctx */
#define A_fg_gate         0x18ebb   /* byte; bit7 set suppresses the foreground sprite draw # ctx */

/* ---- sprite edge masks (blit_obj_* @ 0x10bdc..) ---- */
#define A_blit_mask_L     0x15bba   /* left-edge blit masks, indexed (x&0xf)<<2 */
#define A_blit_mask_R     0x15bfa   /* right-edge blit masks */

/* ---- road / perspective (build_road_geometry @ 0x11f4c) ---- */
#define A_road_seg_data       0x18d1c   /* per-leg road segment slopes (shorts): [0] + [1..12] */
#define A_view_flags          0x18c56   /* leg/view selector (0,2,4,6) */
#define A_view_parity         0x18c60   /* per-view parity word (draw_game_objects +=2/frame; handler_lo reads &2) */
#define A_road_curve          0x18c6a   /* signed current road curvature */
#define A_horizon             0x1905e   /* horizon position input */
#define A_road_seg_head       0x18cb6   /* cached road_seg_data[0] */
#define A_scroll_frame        0x18cb2   /* road-scroll frame index (0-15); indexes the per-leg scroll table at buf_a + leg*16 */
#define A_screen_offset       0x18d18   /* road-scroll offset into buf_c (word); = scroll-table byte * 0x1900, read by blit_road_scroll */
#define A_scroll_speed        0x18cb4   /* horizontal road-scroll speed (signed word) */
#define A_hscroll_pos         0x18cb8   /* horizontal fine-scroll position, wrapped into [0, 0x280) */
#define A_hscroll_step2       0x18cac   /* road_seg_head * scroll_speed * 2 (word); per-frame scroll step, doubled # ctx */
#define A_road_scanline_tbl   0x190ac   /* per-row cumulative slope (shorts) */
#define A_road_curve_tbl      0x18efc   /* 106 longwords: per-row curve offset (accumulated) */
#define A_road_curve_tbl_end  0x190a4   /* one past road_curve_tbl; perspective fill runs downward */
#define A_road_width_tbl      0x18f24   /* per-row road half-width (shorts, stride 4) */
#define A_road_width_src      0x18d5a   /* width source values (shorts, stride 0x20) */
#define A_ground_scan_tbl     0x18d48   /* 13 ground/horizon scanline descriptors (stride 0x20); draw_ground reads the marker at +3 */
#define A_ground_view_off     0x18c58   /* view_flags * 0xdd; column index into the ground offset table */
#define A_persp_seg_tbl       0x17156   /* const: signed per-segment run lengths */
#define A_width_count_tbl     0x1718a   /* const: per-row width run counts, 4 view banks of 16 */
#define A_horizon_row         0x18c6c   /* output: clamped horizon scanline */
#define A_horizon_frac        0x18c6e   /* output: horizon sub-row parity */
#define A_ckpt_scroll         0x18c72   /* checkpoint-banner scroll position (word); += 4/frame, wraps */

/* ---- game_update @ 0x1110e per-frame state (see the reconstruction for roles) ---- */
#define A_marker_pending    0x18d14   /* b: gate -> handle_marker(); also set from the course stream */
#define A_crash_phase       0x18c86   /* w: crash/despawn phase (signed; ==3 special) */
#define A_rev_reload        0x18d12   /* w: engine idle/rev-target reload (set to 8) */
#define A_engfreq           0x1b07d   /* b: EGFREQ engine-sound frequency (adjacent to EGFLAG 0x1b07c) */
#define A_event_pending     0x18c82   /* w: pending-event id dispatched via A_event_jumptable */
#define A_fire_hold         0x18c98   /* w: fire-hold / dashboard-variant countdown (init 4) */
#define A_dsp_variant_idx   0x18c7e   /* w: +8&0x38 HUD dashboard-variant cursor */
#define A_leg_flags_sel     0x18c96   /* w: +4&4 toggle; selects the legflag record */
#define A_timeout_gate      0x18c3e   /* w: must be 0 to arm the time-out (hud_crash_timer = 0x5b) */
#define A_lean_phase        0x18cce   /* w: +1&0xf lean-table phase (indexes A_lean_anim_tbl) */
#define A_spin_word2        0x18cca   /* w: second spin word; hi half of the 0x18cc8 spin long */
#define A_turn_flags        0x18c80   /* w: auto/view turn flag bits (_DAT_00018c80) */
#define A_curve_window      0x18c88   /* l: curve-window pair [0]/[2] for the road_curve+0x4000 test */
#define A_curve_clamp_flag  0x18d1a   /* w: set when road_curve clamped; gates the rpm brake */
#define A_speed_jitter_ph   0x18c94   /* w: +1&0xe high-speed jitter phase (indexes A_speed_jitter_tbl) */
#define A_scroll_phase      0x18c8e   /* w: +2&0xe scroll-table phase (indexes A_scroll_speed_tbl) */
#define A_view_wrap_flag    0x18c9a   /* w: -1 when view_flags wrapped (gates render vs course-stream tail) */
#define A_view_bank         0x18c54   /* w: +8&8 view-bank toggle on wrap */
#define A_steer_hold        0x18ccc   /* w: steer-hold counter; >=10 gates the spin */
#define A_curve_freeze      0x18d16   /* w: nonzero freezes road_curve integration (_DAT_00018d16) */
#define A_road_edge_flags   0x1905c   /* w: road-geom output; sign + bits 0x1000/0x2000/0x4000 gate off-road push */
#define A_road_geom_hi      0x19094   /* l: road-geom output; hi word < 0 gates the edge-push branch */
#define A_course_flag_bit   0x18c70   /* b: course-flag bit cursor (wraps at the course byte value) */
#define A_course_src_ring   0x18edc   /* course-geometry source ring feeding road_curve_tbl (stride 0x20/iter) */
#define A_course_row_ctr    0x18c52   /* w: course-record row countdown (-8; <0 pulls the next record) */
#define A_marker_slope_src  0x18d32   /* w: marker-slope source (+2 copied to +0) */
#define A_palette_cursor    0x18cba   /* w: +1&0x1f palette-record cursor (indexes buf_a+0x50) */
#define A_palette_toggle    0x18c5c   /* w: palette-swap double-buffer toggle */
#define A_palette_scratch   0x17fb0   /* palette-record staging buffer (from buf_a+0xf2 record) */
/* spin/collision effect block @ 0x19114 (0x2e bytes; built each frame, dispatched via jumptable) */
#define A_fx_block          0x19114   /* l: block base; event bytes dispatched via A_event_jumptable */
#define A_fx_block_04       0x19118   /* l: +4 (obj_flags[0]) */
#define A_fx_block_06       0x1911a   /* w: +6; ==0x3d triggers the 0x3d fill */
#define A_fx_block_08       0x1911c   /* l: +8 */
#define A_fx_block_0a       0x1911e   /* +0xa: start of the 0xc-word copy dst */
#define A_fx_block_0c       0x19120   /* l: +0xc */
#define A_fx_block_10       0x19124   /* l: +0x10 */
#define A_fx_block_1a       0x1912e   /* l: +0x1a (0x3e fill start) */
#define A_fx_block_1e       0x19132   /* l: +0x1e */
#define A_fx_block_22       0x19136   /* l: +0x22 */
#define A_fx_block_26       0x1913a   /* l: +0x26 (==0x3d triggers the 0x3e fill) */
#define A_fx_block_2a       0x1913e   /* l: +0x2a */
#define A_fx_block_2e       0x19142   /* b: +0x2e (end byte) */
#define A_event_type        0x18eca   /* w: 0x1a=checkpoint, 0x1d=collision (DAT_00018ec8._2_2_) */
#define A_score_overlay_dig 0x18215   /* b: bonus score-overlay digit char */
/* const tables (image data) game_update indexes */
#define A_legflag_tbl       0x173a4   /* long records -> leg_flags_c90; indexed by leg_flags_sel */
#define A_lean_anim_tbl     0x173ac   /* byte lean table; idx = lean_phase + (rpm&0x70) */
#define A_speed_jitter_tbl  0x17394   /* word speed-jitter adds; idx = speed_jitter_ph & 0xe */
#define A_scroll_speed_tbl  0x1742c   /* word scroll-speed table; idx = scroll_phase + (rpm&0x70) */
#define A_steer_curve_tbl   0x174ec   /* byte steer-curve; idx = (rpm>>4)+(skid<<3)+(wheel<<3) */
#define A_fx_type_tbl       0x18640   /* spin/collision fx records (0x18-byte); idx from obj flag bits>>5 */
#define A_crash_anim_tbl    0x18690   /* crash-anim records; indexed by collision_lock */
#define A_event_jumptable   0x11aa2   /* word offsets to the evt_* handlers (from this base) */
#define A_time_subctr       0x18cfe   /* w: time-drain sub-counter (+1/frame, fires every 0xc) */
#define A_steer_delta       0x18cae   /* w: per-frame steering delta added into road_curve */
#define A_course_read_pos   0x18c50   /* w: byte offset into the packed course stream (+8 & 0x1ff8) */

#endif /* BB_ADDRS_H */