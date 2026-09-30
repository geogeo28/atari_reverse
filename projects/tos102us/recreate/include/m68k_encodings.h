/* m68k_encodings.h — the 68000 words the ROM's assembler chose where GNU as chooses another, spelt ONCE
 * for every byte-pinned transcription (`src/vdi/helpers.S`, `palette.S`, `raster.S`, `src/aes/optimize.S`).
 *
 * THE SPELLING POLICY. A transcription ships the ROM's own instructions and is pinned to the ROM BYTE
 * FOR BYTE (`test/transcription.py`'s `assert_transcribed`). Where gas, handed the instruction, would emit a
 * different word of the same meaning, the `.S` does not excuse the word in the pin: it spells the ROM's
 * encoding as `.word <ENCODING>(register), <operand>` with the instruction in its comment. An excusal
 * is left only for a word NO spelling can reproduce — a displacement or address that measures to where
 * the `.S` itself is linked — and each of those is pinned to the exact value it must hold.
 *
 * Two families reach the ROM's code:
 *   * `<op>.w #<imm>,Dn` for AND, ADD and CMP. The ROM's assembler put the immediate in the EA field of
 *     the register form (`$c07c`, `$d07c`, `$b07c` with Dn in bits 11..9); gas picks ANDI/ADDI/CMPI.
 *     Same length and the same flags — and NOT always the same cost to the instrument: Musashi charges
 *     the EA forms of AND and ADD 10 cycles where ANDI/ADDI cost 8 (CMP is 8 either way), so a
 *     transcription spelt gas's way runs FASTER than the ROM and its Tier 3 row reads 0.99, not 1.00.
 *   * `d16(An)` with a displacement of 0, which gas drops to `(An)` — a shorter instruction, so every
 *     byte after it would move.
 *
 * Register numbers are the 68000's: D0..D7 and A0..A7 are 0..7, spelt `M68K_D<n>` / `M68K_A<n>`. The fields are ADDED, not OR-ed: they are
 * disjoint bits, and `|` starts a comment in m68k GNU as, where every one of these is used.
 */
#ifndef TOS102US_M68K_ENCODINGS_H
#define TOS102US_M68K_ENCODINGS_H

#define M68K_DATA_REGISTER_SHIFT 9        /* the destination Dn / An field, bits 11..9 */

/* The register numbers the fields hold, one spelling for every `.S` */
#define M68K_D0 0
#define M68K_D1 1
#define M68K_D2 2
#define M68K_D3 3
#define M68K_D4 4
#define M68K_D5 5
#define M68K_D6 6
#define M68K_D7 7
#define M68K_A0 0
#define M68K_A1 1
#define M68K_A2 2
#define M68K_A3 3
#define M68K_A4 4
#define M68K_A5 5
#define M68K_A6 6
#define M68K_A7 7

/* `and.w #<imm>,Dn` / `add.w #<imm>,Dn` / `cmp.w #<imm>,Dn`: the register form with EA mode 7, reg 4 */
#define M68K_AND_W_IMMEDIATE(dn)   (0xc07c + ((dn) << M68K_DATA_REGISTER_SHIFT))
#define M68K_ADD_W_IMMEDIATE(dn)   (0xd07c + ((dn) << M68K_DATA_REGISTER_SHIFT))
#define M68K_CMP_W_IMMEDIATE(dn)   (0xb07c + ((dn) << M68K_DATA_REGISTER_SHIFT))
/* ...and `and.l #<imm>,Dn` the same way: the span clear's block mask ($fc4ba6) */
#define M68K_AND_L_IMMEDIATE(dn)   (0xc0bc + ((dn) << M68K_DATA_REGISTER_SHIFT))

/* `move.w <d16>(An),Dn` and `movea.l <d16>(An),Am`, for the displacement of 0 gas would drop */
#define M68K_MOVE_W_D16(an, dn)    (0x3028 + ((dn) << M68K_DATA_REGISTER_SHIFT) + (an))
#define M68K_MOVEA_L_D16(an, am)   (0x2068 + ((am) << M68K_DATA_REGISTER_SHIFT) + (an))
/* ...and `sub.w <d16>(An),Dn` / `add.w <d16>(An),Dn`, $a006's two reads of an edge's x1 at 0(a0) */
#define M68K_SUB_W_D16(an, dn)     (0x9068 + ((dn) << M68K_DATA_REGISTER_SHIFT) + (an))
#define M68K_ADD_W_D16(an, dn)     (0xd068 + ((dn) << M68K_DATA_REGISTER_SHIFT) + (an))
/* ...and the store the other way, `move.w Dn,<d16>(An)`: the sprite's row count into 0(a2) ($fd0068) */
#define M68K_MOVE_W_TO_D16(dn, an) (0x3140 + ((an) << M68K_DATA_REGISTER_SHIFT) + (dn))
/* `sub.w #<imm>,Dn` in the register form, AND's and ADD's family: the sprite's clip ($fcffd8, $fd0002) */
#define M68K_SUB_W_IMMEDIATE(dn)   (0x907c + ((dn) << M68K_DATA_REGISTER_SHIFT))
/* `move.l <d16>(An),Dn` and `tst.l <d16>(An)` at 0: $a00e's reads of an MFDB's base ($fd0394, $fd04f6) */
#define M68K_MOVE_L_D16(an, dn)    (0x2028 + ((dn) << M68K_DATA_REGISTER_SHIFT) + (an))
#define M68K_TST_L_D16(an)         (0x4aa8 + (an))
/* `cmp.b #<imm>,Dn` / `cmp.l #<imm>,Dn` in the register form, CMP.W's family: merge_str's codes ($fed090..),
 * unfmt_str's space ($fecf68), ldiv's divide bound ($fe3e50) */
#define M68K_CMP_B_IMMEDIATE(dn)   (0xb03c + ((dn) << M68K_DATA_REGISTER_SHIFT))
#define M68K_CMP_L_IMMEDIATE(dn)   (0xb0bc + ((dn) << M68K_DATA_REGISTER_SHIFT))
/* `movea.l #<imm>,An`, which gas shortens to `movea.w` for an immediate that fits a word: the object-text helpers'
 * field offsets ($fecf88) */
#define M68K_MOVEA_L_IMMEDIATE(an) (0x207c + ((an) << M68K_DATA_REGISTER_SHIFT))
/* Two words a transcription carries as BYTES of a routine it does not enter: `bsr.w` (its displacement word after
 * it), and the Line-F exception word, GEM's call (`$F000` + the call table's byte offset, `aes/aes.h`) */
#define M68K_BSR_W                 0x6100
#define M68K_LINE_F_WORD           0xf000
/* `jsr <xxx>.l`, which gas turns into `jsr <d16>(pc)` for a label of the same section: merge_str's calls of the
 * Alcyon runtime ($fed0e6, $fed0f0) */
#define M68K_JSR_ABSOLUTE_LONG     0x4eb9

#endif /* TOS102US_M68K_ENCODINGS_H */
