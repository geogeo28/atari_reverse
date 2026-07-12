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

/* ---- fill patterns ---- */
#define A_color_pairs     0x15afa   /* 8-byte (4-plane) solid-fill pattern per colour index */

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