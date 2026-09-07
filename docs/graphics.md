# Graphics

ST bitmaps are **planar**. Understanding the plane layout, palette, and any compression
lets you extract a game's art to PNG. Reference tool: `tools/extract_graphics.py`.

## Low-res planar format (320×200, 16 colours)

- 4 **bitplanes**. A pixel's 4-bit colour index = one bit taken from each plane.
- **Screen (interleaved)**: memory goes word0=plane0, word1=plane1, word2=plane2,
  word3=plane3, then the next 16 pixels, … (32000 bytes total).
- **Storage (contiguous/planar)**: assets are often stored as 4 separate planes back to
  back (plane0 = 8000 bytes, then plane1, …). Games convert contiguous→interleaved when
  drawing (look for copies with strides of `+8000/+16000/+24000` bytes — that's the tell).
- Plane 0 is the **LSB** of the colour index (standard). Getting plane order wrong
  scrambles colours but not shapes, so a greyscale-by-index render still looks "right"
  structurally — verify colour separately.

`extract_graphics.py` decodes a full-screen block as 4 contiguous planes → 320×200 indices
→ PNG. Feed it a palette (below) or it renders greyscale.

### The shared pixel model — `tools/st_pixels.py`

The layouts above vary along exactly two axes, and `tools/st_pixels.py` is the one place this
workspace spells either of them out — import it from a project's extractor rather than re-deriving
them (Zynaps' `projects/zynaps/tools/dat2png.py` and Wonder Boy's
`projects/wonderboy/tools/extract_gfx.py` both do).

- **Granularity.** A group of interleaved planes is either **word** granular (`unit_bits=16`: four
  big-endian plane words, 16 pixels — screens, tiles, most bitmaps) or **byte** granular
  (`unit_bits=8`: four consecutive plane bytes, 8 pixels — fonts, digit glyphs, other 8-px-wide
  cells). Within a group the **leftmost pixel is the most significant bit**.
- **Masked or not.** A sprite puts one extra **mask** field *ahead* of the four plane fields of
  every group, so a group is five fields wide, and a **set** mask bit means transparent (the drawing
  code ANDs the mask, then ORs the data — "Masked sprites" below). `decode_planar` returns
  `TRANSPARENT` for those pixels, which is `-1` **on purpose and never a palette subscript**: a
  masked pixel has no colour index at all, and `to_rgb_image` refuses a decode containing one rather
  than let `palette[-1]` quietly paint the last entry.

Two of its refusals are worth knowing about, because both failures are otherwise invisible in the
PNG: a slice too short for the requested `width × rows` raises instead of decoding the missing bytes
as zeros (a blank, entirely plausible-looking bitmap), and `split_rows` refuses a tall decode that
does not divide into equal frames. Colour lives in the same module — `st_word_to_rgb` is the
`value * 255 // 7` scaling below, and `is_st_colour_word` is the in-range test a palette scan is
built on.

## Palettes

- **ST**: 16 words, each `0x0RGB`, **3 bits/channel** (0–7). `r = (w>>8)&7` etc.,
  scale ×255/7.
- **STE**: 4 bits/channel but bit-rotated — the LSB sits in bit 3 of each nibble:
  intensity = `((v&7)<<1) | ((v>>3)&1)`. If ST decoding looks too dark/off, try STE. Going the other
  way — authoring a palette for a real machine — the encode is `((i>>1)&7) | ((i&1)<<3)`, and the
  useful predicate beside it is "does this word use bit 3 in any channel?", i.e. whether the colour
  is reproducible on a plain ST at all (`projects/blackice/pipeline/stepix/palette.py`).
- Find palettes in the **code** (`.PRG`), not the graphics file: scan for 16 consecutive
  words with the top nibble zero and channel nibbles in range. Confirm by finding the
  `Setpalette` call and reading the pointer it passes (`a0`). Games keep a **table** of
  per-scene/leg palettes; the atlas often shares one master palette.

```bash
python3 tools/extract_graphics.py bin/GRAPHICS.GRA out/gfx \
  --pal-file bin/GAME.PRG --pal-off 0x<palette-file-offset> [--skip 0x<header-bytes>]
```

`--skip` drops a raw header/sprite table that some files carry *before* the RLE stream —
read the unpacker to find it (see below). Decoding without the skip prepends that table as
literals and shifts every screen; the tell-tale is a decompressed size that isn't a clean
multiple of the screen size.

## Compression (RLE is common)

ST assets are frequently run-length encoded with sentinel words. Find the unpacker in the
code (it reads a stream, writes runs) and mirror its rules. BuggyBoy's `GRAPHICS.GRA`:

- `0x1234 N` → `N+1` words of `0x0000`; `0x1234 0` → literal `0x1234`
- `0x5678 N` → `N+1` words of `0xFFFF`; `0x5678 0` → literal `0x5678`
- `0x1234 0x1234 0x1234` → end of stream; anything else → literal word

That decompressed 182 KB → **8× 320×200 screens** (logo, sprites, scenery, HUD, font).
The file opens with a **0xd00-byte (3328) raw sprite table** before the RLE stream — the
unpacker (`unpack_graphics` @ `0x10620`) pre-copies it into a work buffer, then decompresses
the stream that follows. Pass `--skip 0xd00` to line up on it. The table is **208 records ×
16 B** (four plane accumulators, stored as four high words then four low words), not 416 × 8:
`build_sprite_shifts` consumes 16 B per record and emits 16 pre-shifted copies of 16 B, so
record *i* owns exactly `buf_b + i*0x100` and 208 × 0x100 = 0xd000 = `buf_c − buf_b`. A read
in that shift buffer therefore names its header record without ambiguity — the property the
usage audit (`projects/buggyboy/tools/sprite_audit.py`) rests on. In the same file, page 1's
planes 2 and 3 are `0xff` throughout and the unpacker's compaction drops them: 2-plane data in
a 4-plane container, nothing lost.
These 8 screens are **sprite/tile atlases** (dense source art the game composites and
scales at runtime), not finished framebuffers — expect e.g. the intro "LEG"/digit text at
several zoom sizes packed into one atlas. Tables of small `0x1234`-delimited records =
individual sprites/tiles.

## Masked sprites

Objects that overlay a background use a **mask + data** pair (often adjacent longwords):
`AND` the mask, `OR` the data. Edge masks (e.g. two small lookup tables) anti-alias the
scaled object's left/right boundary. Scaling for pseudo-3D is done by choosing how many
screen rows each source row covers, from a perspective table.

The common hand-asm shape is **one unrolled body per width class**, entered at several points. A
sprite of width class *n* stores `n+1` five-word groups per row — mask, then planes 0–3 — so its
source stride is `(class+1) * 10` bytes, which is exactly what a top clip subtracts from the source
pointer per clipped row and the cleanest statement of the layout there is; the sub-word shift is one
`ror.l` of `x & 0xf` applied to all five words, and it makes the sprite span **one group more on
screen** than it stores. The clipped variants are the same body behind a **ladder of rungs**, one per
group the edge eats, and two things about them are worth knowing before you transcribe one. The gate
is often a
**byte in memory re-read once per group**, not a value latched on entry — Flying Shark's edge
blitters consult `blit_clip_mask` inside the loop, and a reconstruction that hoisted that read was
byte-identical on every sprite the game ships and unfaithful to the instruction (one of the six slips
in [`methodology.md`](methodology.md), "Contract coverage"). And **the ladders are not symmetric**:
two of that game's four right-hand ladders narrow the restore record they have just appended and two
do not, so the wider sprites really do restore up to 24 bytes past the row they drew — an original
bug, and the reason the rungs are transcribed as a table rather than generated from the width.

## Scrolling by moving the video base, not the pixels

A vertically scrolling game need not copy a byte to scroll. The shape to recognise — Flying Shark is
the worked example (`projects/flyingshark/notes/gameplay.md` §4 and `notes/frontend.md` §2) — is
**one circular framebuffer with several bases living inside it**:

- The boot carves a `0x1f900`-byte region (808 scanlines) immediately below `Physbase` and rounds the
  base **up** to 256 bytes, because the shifter's base register (`$ffff8201/8203`) holds only the two
  high bytes and cannot point anywhere finer. Four screen bases sit in it, at `+0x7800`, `+0xfa00`,
  `+0x17700` and `+0x1f400`.
- Each displayed frame takes the next base round-robin, moves it **down** `0x500` bytes (8 scanlines),
  wraps it by the region size when it passes the bottom, and publishes it with
  `Setscreen(-1, base, -1)`. The picture scrolls and nothing is copied.
- **The seam is what it costs.** A base near the bottom of the region is read by the shifter *across*
  the region's end, so a frame that is in that window opens by copying the `0x500` bytes at the base
  up to `base + 0x1f900`. A ring is only circular if the wrap-around rows are kept in step.
- The **sub-tile phase** is separate arithmetic: a counter stepped 2 px a frame and masked (`0..0x1f`
  here) indexes a 16-entry split table that says how many rows of the tile above and of the tile below
  make up the newly exposed 8-scanline band; the map cursor steps one row whenever the counter wraps.

Two consequences. A reconstruction must read every base **out of the image** and never compile one in
— the region's address is a function of `Physbase`, which is the machine's answer and not the
program's — and the whole scrolling surface is live game memory that is *not in the `.PRG` at all*,
which a differential harness has to place deliberately (`projects/flyingshark/recreate/README.md`,
"The image model"). Off target that harness can pin the *arithmetic* and not the address it lands on;
the surface that sees a ring in the wrong place is rendered pixels — a scroll that tears or wraps at
the wrong row ([`on-target-execution.md`](on-target-execution.md), "The observable surfaces").

### Deferred drawing: display list, restore list, repair grid

The renderer above is usually paired with a **display list**, and recognising the trio saves reading
each drawing site: a fixed array of small records (Flying Shark: 223 × `x.w y.w frame.b active.b`),
sub-ranges owned by subsystem, which every game routine *publishes into* rather than drawing. The
active byte is also the layer — 0 hidden, negative drawn in pass A, `1..0x7f` in pass B — and one
renderer walks the list twice.

- **The restore list** is how the ring is paid for: each sprite drawn appends
  `(screen offset, width class, row count)` to the list belonging to the buffer it drew into, and the
  renderer replays that list two frames later to copy clean background over the dirt — source and
  destination differing by exactly the scroll that separates the two buffers (`+0x280` = 4 scanlines
  here), so the same world content lands in the same place.
- **The repair grid** is how a sprite gets *behind* the scenery: pass A copies the overlay tile ids of
  the map cells the sprite touched into a grid, which is drained after the pass and re-blitted with
  colour 0 transparent, over the sprites. Pass B then draws on top of everything.

The transferable part is that **no game routine touches the screen**: one function does, once, in a
fixed order — which is why a single differential over that function can cover a whole frame.

→ Sound assets: [`sound.md`](sound.md). Naming the drawing code: [`methodology.md`](methodology.md).