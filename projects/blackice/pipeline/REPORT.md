# REPORT — stepix asset pipeline

## What was built

A Python package `stepix/` plus a test suite and one C file that ships to the target, all
under `assets/`. `README.md` is the byte-exact format contract the C engine will be written
against; the Python is its reference implementation.

| Module | Role |
|--------|------|
| `palette.py` | STE colour word codec, `StePalette` (index 0 pinned as background/border), perceptual ramp builder, 16-word binary + C array export |
| `colourspace.py` | sRGB ↔ CIE Lab, shared so palette/quantize/texture use one distance metric |
| `quantize.py` | RGB → palette indices in Lab, ordered Bayer 2x2/4x4 dither, off-palette auditor |
| `planar.py` | indexed ↔ 4-plane word-interleaved, 320x200 screen, DEGAS `.PI1` read/write |
| `texture.py` | 64x64 column-major texels, shade table (dark-side cue), `.TEX` blob, C arrays |
| `sprite.py` | billboards with per-column span tables, `.SPR` blob; HUD planar data + 1-plane AND mask |
| `font.py` | 8x8 1-plane font, 96 glyphs (ASCII 32..127), 768 bytes |
| `pack.py` | `.PAK` archive + LZSS codec |
| `demo_assets.py` | the whole demo set, procedural and seeded |
| `depack.c` / `depack.h` | the engine-side depacker; `depack_main.c` is the test harness |

## Format contract (summary — byte-exact tables in README.md)

- **Palette word** `$0RGB`, each nibble `= (intensity >> 1) | ((intensity & 1) << 3)`.
  So `15,15,15 = $0FFF`, `14,14,14 = $0777`, **`8,8,8 = $0444` (not `$0888`)**, `2,4,6 = $0123`.
  On-disk palette = 16 big-endian words, 32 bytes, index 0 = border.
- **Screen** 4 planes word-interleaved, plane 0 = LSB, bit 15 = leftmost pixel,
  160 bytes/row, 32,000 bytes. `.PI1` = 2-byte res + 32-byte palette + 32,000 = 32,034.
- **Texture** `STXT`: 12-byte header + 12 bytes/entry (name8 + u32 offset), texels 64x64
  **column-major**, `(x,y)` at `x*64+y`, 4,096 bytes; the dark variant sits at `offset+4096`.
- **Sprite** `STSP`: 12-byte header + 12 bytes/entry; record = 128-byte span table
  (64 x first/last opaque row) + 4,096 texels = 4,224 bytes. **Transparent index 15**;
  an empty column is `first=$FF, last=$00`, so the skip test is `first > last`.
- **HUD blit**: interleaved planar data (holes forced to index 0) + a **1-plane** mask,
  bit set = transparent; draw is `and.w mask,(dst) / or.w data,(dst)` per plane. No
  pre-shifting — HUD art is fixed to 16-pixel boundaries.
- **PAK** `STPK`: 8-byte header + 24-byte entries (name8, offset, packed_len, raw_len,
  method, reserved). Every payload offset is even. Method 1 = LZSS: MSB-first control byte,
  literal or a `((len-3)<<12)|(offset-1)` token, window 4,096, match 3..18, **no end marker**
  (raw_len drives it), byte-at-a-time copies so overlapping matches work.

## Numbers measured

**Tests: 542, all passing** (`python3 -m pytest tests/ -q`, ~1.3 s), across 9 files:
palette 62, font 315, texture 20, planar 20, README-contract 17, quantize 15, sprite 15,
pack 59, demo 19.

**Compression** (`out/demo.pak`, LZSS unless the member would grow):

| resource | raw | packed | ratio | method |
|----------|-----|--------|-------|--------|
| PALETTE  | 32 | 32 | 1.000 | stored |
| TEXTURES | 32,828 | 5,500 | 0.168 | lzss |
| SPRITES  | 4,248 | 684 | 0.161 | lzss |
| FONT     | 768 | 433 | 0.564 | lzss |
| HUDSCR   | 32,000 | 5,090 | 0.159 | lzss |
| ICONDATA | 512 | 132 | 0.258 | lzss |
| ICONMASK | 128 | 39 | 0.305 | lzss |
| **TOTAL** | **70,516** | **11,910** | **0.169** | |

The four textures with their dark variants plus a full HUD screen fit in **10.6 KB packed**.
Incompressible input is stored rather than inflated (verified: 3,000 random bytes → stored).

**Depacker size**: `m68k-elf-gcc -m68000 -O2` compiles `depack.c` to **118 bytes of text**,
zero data, zero bss.

**Determinism**: two consecutive `python3 -m stepix.demo_assets out` runs produce a
byte-identical `demo.pak` (sha256 `e9626ac5…`).

## Bugs found and fixed during the build

1. **Shade table could brighten.** The dark-side table was a plain nearest-Lab search after
   darkening; on a coarse 16-colour ramp it mapped brick index 3 (L\* 62.7) to index 4
   (L\* 65.8) — *lighter*, inverting the N-S/E-W cue, and left most entries mapping to
   themselves. Now the search is constrained to strictly darker entries. Pinned by
   `test_shade_table_never_brightens` and `..._darkens_every_index_that_can_be_darkened`.
2. **Ramp shades collided.** Dedupe compared only against the previous shade, so a nudged
   colour could re-collide with an earlier one (hue 0, saturation 1.0, 6 shades produced
   `(15,0,0)` twice). Now compared against every earlier shade; clean over a 288-case sweep.
3. **`lz_unpack` raised `IndexError` on a truncated stream** instead of the documented
   `ValueError` — it bounds-checked only the control byte, not literals or match tokens.
4. **Art defects caught by looking at the PNGs**, not by tests: stone blocks fell to
   near-black and read as holes in the masonry, and the door/barrel grain read as wormholes
   (both because the 3-shade ramps' floor sat at L\* ≈ 7); the HUD floor band was a blown-out
   gold. Fixed by raising the stone/wood ramp floors and retuning the bands.

## Verification

- **Mutation sweep, 12/12 caught, no survivors**: swizzle → identity, unswizzle → identity,
  plane order reversed, pixel bit order mirrored, column-major → row-major, shade table
  allowed to brighten, span last-row off-by-one, mask polarity inverted, depack length
  off-by-one, depack offset bias dropped, PAK alignment dropped, and `LZ_MIN_MATCH` changed
  in **`depack.c`** (caught by the Python→C cross-check).
- **Python-pack → C-depack** is asserted identity on 8 synthetic corpora, 8 fuzzed inputs,
  and the real generated texture blob and HUD screen. The C is compiled in the test with
  `-Wall -Wextra -Werror`.
- **Every PNG preview was viewed** with the Read tool: palette strip, all four textures
  (lit and dark side by side), the barrel sprite, the HUD icon, the font sheet, and the
  320x200 backdrop. The art reads as brick / riveted steel / ashlar stone / planked door,
  the barrel silhouette is curved, and the font is legible.

## Unverified / caveats

- **The STE swizzle is verified against documentation only, not against real hardware.**
  Source: `docs/graphics.md` in this workspace ("the LSB sits in bit 3 of each nibble"),
  which agrees with the Hatari shifter model and with the BRIEF. Every pair in the test
  table was hand-computed from that rule, so the tests prove the code matches the *documented*
  rule — they cannot prove the rule. A palette write on an STE (or a Hatari screenshot
  compared against `indices_to_rgb`) would close this.
- **The `.PI1` palette convention is a choice, not a standard.** DEGAS predates the STE;
  writing STE words means an ST-only viewer shows the art slightly wrong. `palette.to_st_word`
  produces the ST-legal alternative, applied by the caller before writing (the writer itself no
  longer carries a flag for it). Neither variant has been opened in a real ST paint tool.
- **The depacker has been run natively (arm64 `cc`) and cross-*compiled* for m68000, never
  executed on a 68000.** The 168-byte figure (`m68k-elf-gcc -m68000 -Os`, 176 at `-O2`) is a
  compile-time measurement; `tests/test_pack.py` re-runs that cross-compile when the toolchain
  is present, and skips loudly when it is not.
- **No engine exists yet**, so the column-major claim is an argument about addressing, not a
  measured cycle count. The premise that a contiguous column beats a 64-byte stride, and the
  chunky+c2p requirement from the BRIEF, are untested here.
- **Sprite scaling is not implemented** — the span table is emitted and verified, but nothing
  yet consumes it; likewise the HUD mask/data pair has no drawing code to validate against.
- `render_text` in the font renders **uppercase only** (lowercase aliases to uppercase);
  fine for the HUD vocabulary, a limitation if lowercase is ever wanted.
- The `.PAK` has **no checksum**, deliberately: these are assets shipped with the game, and a
  content hash would cost the 68000 time for nothing. The depacker does **not** trust its
  input structurally, though: a truncated stream and a match reaching before `dst` are
  rejected (`STEPIX_DEPACK_BAD_STREAM`) and an overshooting match is clamped, all with
  per-token checks costing 50 bytes of text. A malformed stream can therefore only produce
  wrong pixels, never a write outside the destination buffer — verified under
  `-fsanitize=address` on the two streams that used to overflow.
