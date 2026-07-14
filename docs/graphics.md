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

## Palettes

- **ST**: 16 words, each `0x0RGB`, **3 bits/channel** (0–7). `r = (w>>8)&7` etc.,
  scale ×255/7.
- **STE**: 4 bits/channel but bit-rotated — the LSB sits in bit 3 of each nibble:
  intensity = `((v&7)<<1) | ((v>>3)&1)`. If ST decoding looks too dark/off, try STE.
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
unpacker (`unpack_graphics` @ `0x10620`) pre-copies it (416 records × 8 B) into a work
buffer, then decompresses the stream that follows. Pass `--skip 0xd00` to line up on it.
These 8 screens are **sprite/tile atlases** (dense source art the game composites and
scales at runtime), not finished framebuffers — expect e.g. the intro "LEG"/digit text at
several zoom sizes packed into one atlas. Tables of small `0x1234`-delimited records =
individual sprites/tiles.

## Masked sprites

Objects that overlay a background use a **mask + data** pair (often adjacent longwords):
`AND` the mask, `OR` the data. Edge masks (e.g. two small lookup tables) anti-alias the
scaled object's left/right boundary. Scaling for pseudo-3D is done by choosing how many
screen rows each source row covers, from a perspective table.

→ Sound assets: [`sound.md`](sound.md). Naming the drawing code: [`methodology.md`](methodology.md).