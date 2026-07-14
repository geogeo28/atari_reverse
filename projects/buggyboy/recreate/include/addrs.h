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

/* ---- gameplay state ---- */
#define A_game_over_flag  0x18c34   /* tst.w'd at add_score entry */
#define A_leg_index       0x18c38   /* current leg (0-4); indexes result strings + palette */
#define A_hiscore_pos     0x18c9c   /* results screen: high-score entry counter; gates the score line # ctx */
#define A_results_mode    0x18c9e   /* results screen: 0 or 2; sets label-row count (8-N) + an extra block # ctx */
#define A_setrez_mode     0x18be6   /* byte set_rez sends to the IKBD via XBIOS Ikbdws (0x19) */

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

/* ---- sound driver (play_event_tune @ 0x11c7a; INITTUNE/INITFX/TURNOFF) ---- */
#define A_vbl_sound_vec   0x18c0c   /* VBL sound handler vector; set to REFRESH */
#define A_cur_tune_id     0x18cfa
#define A_refresh         0x1b086   /* REFRESH VBL handler address (stored into vbl_sound_vec) */
#define A_mzflag          0x1b07a   /* music-active flag */
#define A_fxflag          0x1b07b   /* effect-active flag */

/* ---- fill patterns ---- */
#define A_color_pairs     0x15afa   /* 8-byte (4-plane) solid-fill pattern per colour index */

/* ---- font / text (draw_text @ 0x159fa) ---- */
#define A_font_glyphs     0x176a8   /* 16-byte 1bpp glyphs, indexed char << 4 */
#define A_num_glyph_tbl   0x17c5e   /* per-digit word byte-offset into the pre-rendered num sprites */

/* ---- sprite edge masks (blit_obj_* @ 0x10bdc..) ---- */
#define A_blit_mask_L     0x15bba   /* left-edge blit masks, indexed (x&0xf)<<2 */
#define A_blit_mask_R     0x15bfa   /* right-edge blit masks */

/* ---- road / perspective (build_road_geometry @ 0x11f4c) ---- */
#define A_road_seg_data       0x18d1c   /* per-leg road segment slopes (shorts): [0] + [1..12] */
#define A_view_flags          0x18c56   /* leg/view selector (0,2,4,6) */
#define A_road_curve          0x18c6a   /* signed current road curvature */
#define A_horizon             0x1905e   /* horizon position input */
#define A_road_seg_head       0x18cb6   /* cached road_seg_data[0] */
#define A_road_scanline_tbl   0x190ac   /* per-row cumulative slope (shorts) */
#define A_road_curve_tbl      0x18efc   /* 106 longwords: per-row curve offset (accumulated) */
#define A_road_curve_tbl_end  0x190a4   /* one past road_curve_tbl; perspective fill runs downward */
#define A_road_width_tbl      0x18f24   /* per-row road half-width (shorts, stride 4) */
#define A_road_width_src      0x18d5a   /* width source values (shorts, stride 0x20) */
#define A_persp_seg_tbl       0x17156   /* const: signed per-segment run lengths */
#define A_width_count_tbl     0x1718a   /* const: per-row width run counts, 4 view banks of 16 */
#define A_horizon_row         0x18c6c   /* output: clamped horizon scanline */
#define A_horizon_frac        0x18c6e   /* output: horizon sub-row parity */

#endif /* BB_ADDRS_H */