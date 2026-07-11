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

#endif /* BB_ADDRS_H */