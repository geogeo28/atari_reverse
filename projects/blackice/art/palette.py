"""BLACK ICE - the final 16-colour palette, the depth-band shade tables, and the proofs.

The world is rendered by the machine you are inside, so it owns exactly sixteen colour
registers: a void, a cyan ramp (infrastructure you can use), a magenta ramp (ICE that wants
you dead), and five accents.  Two accents are RESERVED: no wall texture may contain them,
which is what makes a 1-px white rim-light readable against every wall at every depth.

Every channel is a multiple of 0x11 so nothing quantises when it is written to an STE
colour register (4 bits per channel, $0RGB, low-bit-is-MSB swizzle -- see ste_colour_word).

Run as a script to print the luminance table and the ramp-separation proof.
"""

from collections import namedtuple

# --- the STE gamut -----------------------------------------------------------------------
CHANNEL_STEP = 0x11          # 4-bit channel -> 8-bit: v * 0x11
CHANNEL_LEVELS = 16
PALETTE_SIZE = 16

# --- palette indices ---------------------------------------------------------------------
VOID = 0                     # also the border/overscan colour, and floor + ceiling
CYAN_1, CYAN_2, CYAN_3, CYAN_4, CYAN_5 = 1, 2, 3, 4, 5
MAG_1, MAG_2, MAG_3, MAG_4, MAG_5 = 6, 7, 8, 9, 10
DATA = 11                    # yellow: data, glyphs, tokens, emissive
RIM = 12                     # white: RESERVED - enemy rim-light, muzzle, HUD text
ALERT = 13                   # orange: RESERVED - enemy core/iris, trace danger
INTEGRITY = 14               # green: health, safe locks, exit lamps
GRID = 15                    # slate: structural trim, horizon line, HUD trim
                             # ...and the sprite transparency key (see TRANSPARENT_INDEX)

CYAN_RAMP = (CYAN_1, CYAN_2, CYAN_3, CYAN_4, CYAN_5)
MAGENTA_RAMP = (MAG_1, MAG_2, MAG_3, MAG_4, MAG_5)
RAMP_LENGTH = len(CYAN_RAMP)

#: The two accents no wall texture may use.  Enforced by textures.py's self-check.
SPRITE_ONLY = (RIM, ALERT)

#: Sprites are stored with this index meaning "do not draw".  Walls and the HUD may use it.
TRANSPARENT_INDEX = GRID

PaletteEntry = namedtuple("PaletteEntry", "index name rgb role")

PALETTE = (
    PaletteEntry(VOID,      "VOID",      (0x00, 0x00, 0x00), "void / floor / ceiling / border"),
    PaletteEntry(CYAN_1,    "CYAN_1",    (0x66, 0xEE, 0xFF), "cyan ramp 1 - lit trim"),
    PaletteEntry(CYAN_2,    "CYAN_2",    (0x33, 0xCC, 0xEE), "cyan ramp 2 - panel face"),
    PaletteEntry(CYAN_3,    "CYAN_3",    (0x22, 0x99, 0xCC), "cyan ramp 3 - panel body"),
    PaletteEntry(CYAN_4,    "CYAN_4",    (0x11, 0x66, 0x88), "cyan ramp 4 - shadow side"),
    PaletteEntry(CYAN_5,    "CYAN_5",    (0x11, 0x33, 0x66), "cyan ramp 5 - deep recess / fog"),
    PaletteEntry(MAG_1,     "MAG_1",     (0xFF, 0x88, 0xEE), "magenta ramp 1 - ICE lit trim"),
    PaletteEntry(MAG_2,     "MAG_2",     (0xDD, 0x55, 0xCC), "magenta ramp 2 - ICE face"),
    PaletteEntry(MAG_3,     "MAG_3",     (0xBB, 0x33, 0xAA), "magenta ramp 3 - ICE body"),
    PaletteEntry(MAG_4,     "MAG_4",     (0x88, 0x11, 0x77), "magenta ramp 4 - ICE shadow"),
    PaletteEntry(MAG_5,     "MAG_5",     (0x33, 0x00, 0x44), "magenta ramp 5 - ICE recess / fog"),
    PaletteEntry(DATA,      "DATA",      (0xFF, 0xEE, 0x44), "yellow - data, glyphs, tokens"),
    PaletteEntry(RIM,       "RIM",       (0xFF, 0xFF, 0xFF), "white - RESERVED sprite rim / muzzle / HUD text"),
    PaletteEntry(ALERT,     "ALERT",     (0xFF, 0x77, 0x22), "orange - RESERVED enemy core / trace danger"),
    PaletteEntry(INTEGRITY, "INTEGRITY", (0x33, 0xCC, 0x66), "green - integrity, safe lock, exit lamp"),
    PaletteEntry(GRID,      "GRID",      (0x44, 0x44, 0x66), "slate - structural trim / HUD trim / sprite key"),
)

RGB = tuple(entry.rgb for entry in PALETTE)

# --- colour maths ------------------------------------------------------------------------
LUMA_R, LUMA_G, LUMA_B = 0.299, 0.587, 0.114        # Rec.601, the CRT's own weighting
CB_COEFF = (-0.169, -0.331, 0.500)
CR_COEFF = (0.500, -0.419, -0.081)


def luminance(index):
    """Rec.601 luma, 0..255, of a palette index."""
    red, green, blue = RGB[index]
    return LUMA_R * red + LUMA_G * green + LUMA_B * blue


def chroma(index):
    """(Cb, Cr) of a palette index - the hue/saturation half of YCbCr, luma removed."""
    red, green, blue = RGB[index]
    return (sum(c * v for c, v in zip(CB_COEFF, (red, green, blue))),
            sum(c * v for c, v in zip(CR_COEFF, (red, green, blue))))


def chroma_distance(index_a, index_b):
    """Euclidean distance in the (Cb, Cr) plane - separation that survives a mistuned CRT."""
    cb_a, cr_a = chroma(index_a)
    cb_b, cr_b = chroma(index_b)
    return ((cb_a - cb_b) ** 2 + (cr_a - cr_b) ** 2) ** 0.5


def luma_distance(index_a, index_b):
    return abs(luminance(index_a) - luminance(index_b))


def in_gamut(channel):
    """True when an 8-bit channel lands exactly on one of the STE's 16 levels."""
    return channel % CHANNEL_STEP == 0 and 0 <= channel // CHANNEL_STEP < CHANNEL_LEVELS


def ste_colour_word(index):
    """Palette index -> STE $0RGB register word, with the low-bit-is-MSB nibble swizzle.

    Refuses a channel that is not a multiple of CHANNEL_STEP rather than truncating it: a
    silent truncation here is a colour that looks right in the PNG and wrong on the machine.
    """
    word = 0
    for channel in RGB[index]:
        if not in_gamut(channel):
            raise ValueError("%s channel 0x%02X is outside the STE 4-bit gamut"
                             % (PALETTE[index].name, channel))
        level = channel // CHANNEL_STEP                      # 0..CHANNEL_LEVELS-1
        word = (word << 4) | (((level & 1) << 3) | (level >> 1))
    return word


def out_of_gamut_entries():
    """Palette entries with a channel the STE cannot express.  Empty list = the gate passes."""
    return [entry.name for entry in PALETTE if not all(in_gamut(c) for c in entry.rgb)]


def _validate_gamut():
    offenders = out_of_gamut_entries()
    if offenders:
        raise ValueError("palette entries outside the 4-bit gamut: %s" % ", ".join(offenders))


_validate_gamut()


def pil_palette():
    """Flat 48-byte RGB list for PIL's Image.putpalette."""
    return [component for entry in PALETTE for component in entry.rgb]


# --- depth banding -----------------------------------------------------------------------
# Distance fog is an INDEX REMAP, never a new colour.  Five bands; band 0 is the identity.
# A ramp rung r (0 = brightest) becomes BAND_RAMP_STEP[band][r]; VOID_RUNG means "gone".
DEPTH_BANDS = 5
VOID_RUNG = -1

# Band 3 keeps the ramp's BRIGHTEST rung alive rather than collapsing to the two darkest, which
# is what the first revision did.  Collapsing left every cyan wall ~80% one colour, so four
# structurally different walls were 77-87% identical pixel-for-pixel at ten rows (see
# textures.band_agreement).  Fog is still fog: the bulk of a band-3 wall is the darkest rung,
# and only its lit trim, its slate ribs and its data survive as bright marks.
BAND_RAMP_STEP = (
    (0, 1, 2, 3, 4),                                  # band 0 - nearest, identity
    (1, 2, 3, 4, 4),                                  # band 1
    (2, 3, 3, 4, 4),                                  # band 2
    (2, 4, 4, 4, 4),                                  # band 3 - lit trim, then the darkest rung
    (4, 4, VOID_RUNG, VOID_RUNG, VOID_RUNG),          # band 4 - darkest rung, then void
)

# Emissive accents do not fog on the same curve as reflective panel colour: a data glyph is a
# light source, not a lit surface.  RIM, ALERT and INTEGRITY never fog at all - the rim-light is
# the readability guarantee, a far enemy's core is the thing you must still see, and green is the
# exit, which has to be a landmark from across the sector.
#
# NOTHING FOGS TO VOID EXCEPT A RAMP RUNG.  Sending slate (15) to void at band 3 - which the first
# revision did - punched 10-16% of every clean texture's area into black holes shaped exactly like
# `textures.corrupt`'s torn page, so distance manufactured corruption and inverted the premise of
# the world.  Slate and data instead fog UP into the cyan ramp, which is also what keeps a slate
# rib or a yellow via column legible at ten rows (see textures.band_agreement).
BAND_ACCENT_MAP = {
    DATA:      (DATA, DATA, DATA, CYAN_2, CYAN_4),
    INTEGRITY: (INTEGRITY,) * DEPTH_BANDS,
    GRID:      (GRID, GRID, GRID, CYAN_4, CYAN_5),
    RIM:       (RIM,) * DEPTH_BANDS,
    ALERT:     (ALERT,) * DEPTH_BANDS,
}


def shade_table(band):
    """16-entry index remap for a depth band.  table[src_index] -> shaded index."""
    if not 0 <= band < DEPTH_BANDS:
        raise ValueError("band %d outside 0..%d" % (band, DEPTH_BANDS - 1))
    table = [VOID] * PALETTE_SIZE
    steps = BAND_RAMP_STEP[band]
    for ramp in (CYAN_RAMP, MAGENTA_RAMP):
        for rung, index in enumerate(ramp):
            target = steps[rung]
            table[index] = VOID if target == VOID_RUNG else ramp[target]
    for index, per_band in BAND_ACCENT_MAP.items():
        table[index] = per_band[band]
    return tuple(table)


SHADE_TABLES = tuple(shade_table(band) for band in range(DEPTH_BANDS))


def band_indices(band, ramp):
    """The distinct shaded indices a ramp can still produce in this band, void excluded."""
    table = SHADE_TABLES[band]
    return sorted({table[index] for index in ramp} - {VOID})


# --- proofs ------------------------------------------------------------------------------
#: A cyan and a magenta must never be luminance twins: the critique killed a palette on this.
MIN_CROSS_RAMP_LUMA = 12.0
#: ...and must also be separated in hue, because chroma is what a 2x2-doubled CRT smears.
MIN_CROSS_RAMP_CHROMA = 40.0
#: A white rim-light needs this much headroom over the brightest colour a wall may contain.
MIN_RIM_HEADROOM_LUMA = 24.0
#: Any two colours that can appear on the same wall in the same band must clear ONE of these.
#: Luminance survives a mistuned CRT; a wide hue split survives 2x2 pixel doubling.  The first
#: revision only ever measured cyan against magenta and so never saw slate, which sat 8.2 Y from
#: cyan 5 with both of them on the same panel.
MIN_WALL_PAIR_LUMA = 12.0
MIN_WALL_PAIR_CHROMA = 40.0


def cross_ramp_separation(band):
    """(min luma gap, min chroma gap) between the cyan and magenta sets alive in a band."""
    cyans = band_indices(band, CYAN_RAMP)
    magentas = band_indices(band, MAGENTA_RAMP)
    if not cyans or not magentas:
        return (float("inf"), float("inf"))
    pairs = [(c, m) for c in cyans for m in magentas]
    return (min(luma_distance(c, m) for c, m in pairs),
            min(chroma_distance(c, m) for c, m in pairs))


def wall_legal_indices():
    """Every index a wall texture is allowed to contain."""
    return [entry.index for entry in PALETTE if entry.index not in SPRITE_ONLY]


def band_wall_indices(band):
    """The distinct wall-legal colours a band can actually display, void excluded."""
    table = SHADE_TABLES[band]
    return sorted({table[index] for index in wall_legal_indices()} - {VOID})


def pair_margin(index_a, index_b):
    """How comfortably a pair clears the wall-pair rule.  < 1.0 is a failure."""
    return max(luma_distance(index_a, index_b) / MIN_WALL_PAIR_LUMA,
               chroma_distance(index_a, index_b) / MIN_WALL_PAIR_CHROMA)


def worst_wall_pair(band):
    """The tightest pair of colours a wall can show in this band: (a, b, dY, dChroma)."""
    indices = band_wall_indices(band)
    pairs = [(a, b) for position, a in enumerate(indices) for b in indices[position + 1:]]
    if not pairs:
        return None
    first, second = min(pairs, key=lambda pair: pair_margin(*pair))
    return (first, second, luma_distance(first, second), chroma_distance(first, second))


def rim_headroom():
    """Smallest luma gap between the white rim-light and any wall-legal colour."""
    return min(luma_distance(RIM, index) for index in wall_legal_indices())


def _print_luminance_table():
    print("  idx  name        hex      RGB444  STE word   Y      Cb      Cr    role")
    for entry in PALETTE:
        red, green, blue = entry.rgb
        rgb444 = "%X%X%X" % (red // CHANNEL_STEP, green // CHANNEL_STEP, blue // CHANNEL_STEP)
        cb, cr = chroma(entry.index)
        reserved = " *" if entry.index in SPRITE_ONLY else "  "
        print("  %2d%s %-10s #%02X%02X%02X  $%s   $%03X   %6.1f %7.1f %7.1f  %s"
              % (entry.index, reserved, entry.name, red, green, blue, rgb444,
                 ste_colour_word(entry.index), luminance(entry.index), cb, cr, entry.role))
    print("  (* = RESERVED sprite/HUD only - no wall texture may contain it)")


def _print_ramp_ladder():
    ladder = sorted(CYAN_RAMP + MAGENTA_RAMP, key=luminance, reverse=True)
    print("  interleaved luminance ladder (cyan and magenta never adjacent in hue):")
    previous = None
    for index in ladder:
        gap = "" if previous is None else "   gap %5.1f" % (luminance(previous) - luminance(index))
        print("    %-7s Y=%6.1f%s" % (PALETTE[index].name, luminance(index), gap))
        previous = index
    gaps = [luminance(a) - luminance(b) for a, b in zip(ladder, ladder[1:])]
    print("    minimum rung gap: %.1f" % min(gaps))


def _print_band_proof():
    print("  band  %-29s %-29s min dY   min dChroma  verdict" % ("cyan set", "magenta set"))
    all_ok = True
    for band in range(DEPTH_BANDS):
        luma_gap, chroma_gap = cross_ramp_separation(band)
        ok = luma_gap >= MIN_CROSS_RAMP_LUMA and chroma_gap >= MIN_CROSS_RAMP_CHROMA
        all_ok = all_ok and ok
        names = lambda ramp: ",".join(PALETTE[i].name for i in band_indices(band, ramp)) or "-"
        print("   %d    %-29s %-29s %6.1f   %9.1f    %s"
              % (band, names(CYAN_RAMP), names(MAGENTA_RAMP), luma_gap, chroma_gap,
                 "PASS" if ok else "FAIL"))
    print("  thresholds: dY >= %.0f, dChroma >= %.0f -> %s"
          % (MIN_CROSS_RAMP_LUMA, MIN_CROSS_RAMP_CHROMA, "ALL BANDS PASS" if all_ok else "FAILURES"))
    return all_ok


def _print_wall_pair_proof():
    print("  band  tightest wall-legal pair        dY     dChroma  margin  verdict")
    all_ok = True
    for band in range(DEPTH_BANDS):
        first, second, luma_gap, chroma_gap = worst_wall_pair(band)
        margin = pair_margin(first, second)
        all_ok = all_ok and margin >= 1.0
        print("   %d    %-10s vs %-10s %7.1f %8.1f %7.2f  %s"
              % (band, PALETTE[first].name, PALETTE[second].name, luma_gap, chroma_gap, margin,
                 "PASS" if margin >= 1.0 else "FAIL"))
    print("  rule: dY >= %.0f OR dChroma >= %.0f -> %s"
          % (MIN_WALL_PAIR_LUMA, MIN_WALL_PAIR_CHROMA,
             "ALL BANDS PASS" if all_ok else "FAILURES"))
    return all_ok


def _print_shade_tables():
    print("  shade_table(band), one row per band, 16 entries:")
    for band in range(DEPTH_BANDS):
        print("    band %d: %s" % (band, " ".join("%2d" % i for i in SHADE_TABLES[band])))


def main():
    print("BLACK ICE - 16-colour palette")
    print()
    _print_luminance_table()
    print()
    _print_ramp_ladder()
    print()
    print("CYAN vs MAGENTA separation per depth band")
    bands_ok = _print_band_proof()
    print()
    print("EVERY wall-legal pair that can share a wall in a band")
    pairs_ok = _print_wall_pair_proof()
    print()
    print("4-bit gamut: all %d entries on the STE's %d levels per channel, step 0x%02X -> PASS"
          % (PALETTE_SIZE, CHANNEL_LEVELS, CHANNEL_STEP))
    print()
    headroom = rim_headroom()
    print("RIM headroom: white Y=255.0 vs brightest wall-legal colour -> dY = %.1f (need %.1f) %s"
          % (headroom, MIN_RIM_HEADROOM_LUMA, "PASS" if headroom >= MIN_RIM_HEADROOM_LUMA else "FAIL"))
    print()
    _print_shade_tables()
    print()
    fogs_to_void = [PALETTE[index].name for index in wall_legal_indices()
                    if index != VOID and any(SHADE_TABLES[band][index] == VOID
                                             for band in range(DEPTH_BANDS - 1))]
    print("wall-legal colours that fog to VOID before band %d: %s"
          % (DEPTH_BANDS - 1, ", ".join(fogs_to_void) if fogs_to_void else "none (correct)"))
    return 0 if bands_ok and pairs_ok and headroom >= MIN_RIM_HEADROOM_LUMA and not fogs_to_void else 1


if __name__ == "__main__":
    raise SystemExit(main())
