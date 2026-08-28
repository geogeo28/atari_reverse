"""BLACK ICE HUD - the static 320x40 planar strip on the bottom 40 scanlines.

Screen layout (settled in design/DESIGN.md, numbers restated in ART_DIRECTION.md):

    y   0..159   render window: 160x80 chunky pixels, pixel-doubled to 320x160
    y 160..199   this strip: 320x40 planar, drawn at 1:1, sharing the world's 16 colours

Why the strip and not a framed window: the c2p + pixel-double pass is a fixed cost that no
level design or far-clip reduces, and it is paid per rendered *line*.  160x80 emits 25,600
planar bytes a frame against 32,000 for a full-screen 160x100 - a 20% cut to the one cost the
critique called load-bearing - and it buys the HUD for free, because a strip that only changes
when a number changes is a dirty-rect blit, not a per-frame redraw.  No Timer-B raster split
in v1: the HUD's four hues (white, orange, yellow, green) are colours the walls do not own, so
a second palette buys nothing yet.

The strip is drawn at 1:1, so the 8x8 font is legible; the big readouts are drawn at 2x.
"""

from collections import namedtuple

import numpy as np

import drawlib
import font
import palette
import pixelio
from drawlib import Canvas

SCREEN_WIDTH, SCREEN_HEIGHT = 320, 200
WINDOW_CHUNKY_WIDTH, WINDOW_CHUNKY_HEIGHT = 160, 80
PIXEL_DOUBLE = 2
WINDOW_WIDTH = WINDOW_CHUNKY_WIDTH * PIXEL_DOUBLE
WINDOW_HEIGHT = WINDOW_CHUNKY_HEIGHT * PIXEL_DOUBLE
HUD_WIDTH, HUD_HEIGHT = SCREEN_WIDTH, SCREEN_HEIGHT - WINDOW_HEIGHT
HUD_TOP = WINDOW_HEIGHT

# --- strip geometry ---------------------------------------------------------------------------
# The trace meter is the game's escalation system, so it gets the leftmost slot, the widest
# panel, the only 2x readout and the tall bar.  The first revision gave all of that to CYCLES,
# which never changes the way you play, and left the mechanic third on the strip.  The title bar
# lost two rows to pay for it - a sector name does not change mid-sector.
TOP_RULE_HEIGHT = 1
TITLE_BAR_TOP, TITLE_BAR_HEIGHT = 1, 8
PANEL_TOP = 10
PANEL_BOTTOM = HUD_HEIGHT - 2
LABEL_Y = PANEL_TOP + 1
VALUE_Y = LABEL_Y + font.GLYPH_HEIGHT + 1
BIG_SCALE = 2

# Panel widths are set by the font: stepix advances a full 8-px cell, so "INTEGRITY" is 72 px
# and "CYCLES" 48, against 63 and 42 under the 7-px font this package used to carry.  The ammo
# label is abbreviated rather than the bar being starved - CYC is a HUD convention, a 4-pixel
# trace segment is not.
Panel = namedtuple("Panel", "x0 x1")
TRACE_PANEL = Panel(2, 137)
INTEGRITY_PANEL = Panel(140, 219)
CYCLES_PANEL = Panel(222, 255)
TOKEN_PANEL = Panel(258, 287)
WEAPON_PANEL = Panel(290, 317)

BAR_HEIGHT = 12
TRACE_BAR_HEIGHT = 16
TRACE_READOUT_WIDTH = 52
CYCLES_LABEL = "CYC"
BAR_SEGMENTS = 10
SEGMENT_GAP = 1
#: The trace thresholds that step the music tempo and harden the ICE (design/DESIGN.md).
TRACE_THRESHOLDS = (25, 50, 75)
#: Below this the integrity bar turns hostile - the one place the HUD borrows the enemy accent.
INTEGRITY_CRITICAL = 34
TOKEN_COUNT = 3
TOKEN_WIDTH, TOKEN_HEIGHT = 8, 12

HudState = namedtuple("HudState", "sector_name run_clock integrity cycles trace tokens weapon")

DEMO_STATE = HudState(sector_name="SECTOR 7: COLD STORE", run_clock="02:41",
                      integrity=72, cycles=48, trace=73, tokens=(True, True, False),
                      weapon="spike")


# --- text -------------------------------------------------------------------------------------
def draw_text(canvas, x, y, text, ink, scale=1):
    """Stamp font ink onto a canvas at an integer scale.  Returns the pen x after the string."""
    mask = font.text_mask(text)
    if scale > 1:
        mask = np.repeat(np.repeat(mask, scale, axis=0), scale, axis=1)
    height, width = mask.shape
    target = canvas.pixels[y:y + height, x:x + width]
    clipped = mask[:target.shape[0], :target.shape[1]]
    target[clipped] = ink
    return x + width


def right_align(panel, text, scale=1):
    return panel.x1 - font.text_width(text) * scale + scale


# --- panels -------------------------------------------------------------------------------------
def _panel_well(canvas, panel):
    """Every readout sits in the same recessed well, so the strip reads as one machine."""
    canvas.rect(panel.x0, PANEL_TOP, panel.x1, PANEL_BOTTOM, palette.CYAN_5)
    canvas.rect(panel.x0, PANEL_TOP, panel.x1, PANEL_TOP + 1, palette.GRID)
    canvas.rect(panel.x0, PANEL_TOP, panel.x0 + 1, PANEL_BOTTOM, palette.GRID)
    canvas.rect(panel.x1 - 1, PANEL_TOP, panel.x1, PANEL_BOTTOM, palette.CYAN_4)


def _segmented_bar(canvas, x0, x1, y, filled_fraction, ink_for_segment, height=BAR_HEIGHT):
    """A ten-segment bar.  Segments, not a smooth fill: a segment count reads at a glance."""
    span = x1 - x0 + 1
    segment_width = (span - (BAR_SEGMENTS - 1) * SEGMENT_GAP) // BAR_SEGMENTS
    lit = int(round(filled_fraction * BAR_SEGMENTS))
    for segment in range(BAR_SEGMENTS):
        left = x0 + segment * (segment_width + SEGMENT_GAP)
        ink = ink_for_segment(segment) if segment < lit else palette.GRID
        canvas.rect(left, y, left + segment_width - 1, y + height - 1, ink)
        canvas.rect(left, y, left + segment_width - 1, y, palette.CYAN_5 if segment >= lit else ink)
    return segment_width


def _integrity_panel(canvas, state):
    _panel_well(canvas, INTEGRITY_PANEL)
    draw_text(canvas, INTEGRITY_PANEL.x0 + 4, LABEL_Y, "INTEGRITY", palette.CYAN_2)
    critical = state.integrity < INTEGRITY_CRITICAL
    ink = palette.ALERT if critical else palette.INTEGRITY
    _segmented_bar(canvas, INTEGRITY_PANEL.x0 + 4, INTEGRITY_PANEL.x1 - 4, VALUE_Y,
                   state.integrity / 100.0, lambda segment: ink)


def _cycles_panel(canvas, state):
    """Ammo.  Demoted to 1x and to cyan: a number that only ever counts down is not the game,
    and yellow now means DATA and nothing else."""
    _panel_well(canvas, CYCLES_PANEL)
    draw_text(canvas, CYCLES_PANEL.x0 + 4, LABEL_Y, CYCLES_LABEL, palette.CYAN_2)
    reading = "%03d" % min(state.cycles, 999)
    draw_text(canvas, right_align(CYCLES_PANEL, reading) - 4, VALUE_Y + 3, reading, palette.CYAN_1)


def trace_segment_ink(segment):
    """The trace meter recolours itself as it climbs - the escalation the player must read."""
    percent = (segment + 1) * 100 // BAR_SEGMENTS
    if percent <= TRACE_THRESHOLDS[0]:
        return palette.CYAN_2
    if percent <= TRACE_THRESHOLDS[1]:
        return palette.DATA
    if percent <= TRACE_THRESHOLDS[2]:
        return palette.ALERT
    return palette.MAG_1


def trace_readout_ink(trace):
    """The percentage takes the colour of the threshold band it is standing in."""
    for threshold, ink in zip(TRACE_THRESHOLDS, (palette.CYAN_1, palette.DATA, palette.ALERT)):
        if trace <= threshold:
            return ink
    return palette.MAG_1


def _trace_panel(canvas, state):
    """The core mechanic, and so the loudest thing on the strip: 2x digits and a 16-row bar."""
    _panel_well(canvas, TRACE_PANEL)
    draw_text(canvas, TRACE_PANEL.x0 + 4, LABEL_Y, "TRACE", palette.CYAN_2)
    reading = "%d%%" % state.trace
    draw_text(canvas, TRACE_PANEL.x0 + 4, VALUE_Y, reading, trace_readout_ink(state.trace),
              scale=BIG_SCALE)
    bar_x0, bar_x1 = TRACE_PANEL.x0 + TRACE_READOUT_WIDTH, TRACE_PANEL.x1 - 4
    segment_width = _segmented_bar(canvas, bar_x0, bar_x1, VALUE_Y, state.trace / 100.0,
                                   trace_segment_ink, height=TRACE_BAR_HEIGHT)
    for threshold in TRACE_THRESHOLDS:
        segment = threshold * BAR_SEGMENTS // 100
        tick_x = bar_x0 + segment * (segment_width + SEGMENT_GAP) - 1
        canvas.rect(tick_x, VALUE_Y - 2, tick_x, VALUE_Y + TRACE_BAR_HEIGHT, palette.RIM)


def _token_panel(canvas, state):
    _panel_well(canvas, TOKEN_PANEL)
    draw_text(canvas, TOKEN_PANEL.x0 + 3, LABEL_Y, "KEY", palette.CYAN_2)
    for slot in range(TOKEN_COUNT):
        x = TOKEN_PANEL.x0 + 3 + slot * (TOKEN_WIDTH + 1)
        held = state.tokens[slot]
        canvas.rect(x, VALUE_Y, x + TOKEN_WIDTH - 1, VALUE_Y + TOKEN_HEIGHT - 1, palette.GRID)
        if held:
            canvas.polygon([(x + 1, VALUE_Y + 1), (x + TOKEN_WIDTH - 4, VALUE_Y + 1),
                            (x + TOKEN_WIDTH - 2, VALUE_Y + TOKEN_HEIGHT // 2),
                            (x + TOKEN_WIDTH - 4, VALUE_Y + TOKEN_HEIGHT - 2),
                            (x + 1, VALUE_Y + TOKEN_HEIGHT - 2)], palette.DATA)


WEAPON_RAIL_INK = {"buster": palette.CYAN_1, "spike": palette.MAG_1}


def _weapon_panel(canvas, state):
    """A 40-px side view of the equipped gun: cyan bore = Buster, magenta rail = Spike."""
    _panel_well(canvas, WEAPON_PANEL)
    centre = (WEAPON_PANEL.x0 + WEAPON_PANEL.x1) // 2
    top = PANEL_TOP + 4
    canvas.polygon([(centre - 13, top), (centre + 13, top), (centre + 9, top + 6),
                    (centre - 9, top + 6)], palette.CYAN_3)
    canvas.rect(centre - 8, top + 6, centre + 8, top + 14, palette.CYAN_4)
    canvas.rect(centre - 3, top, centre + 2, top + 14, WEAPON_RAIL_INK[state.weapon])
    canvas.polygon([(centre - 11, top + 14), (centre + 11, top + 14), (centre + 8, top + 20),
                    (centre - 8, top + 20)], palette.CYAN_2)
    canvas.rect(centre - 13, top, centre + 13, top + 1, palette.CYAN_1)


def _title_bar(canvas, state):
    canvas.rect(0, 0, HUD_WIDTH - 1, TOP_RULE_HEIGHT - 1, palette.CYAN_3)
    canvas.rect(0, TITLE_BAR_TOP, HUD_WIDTH - 1, TITLE_BAR_TOP + TITLE_BAR_HEIGHT - 1, palette.GRID)
    draw_text(canvas, 3, TITLE_BAR_TOP, state.sector_name, palette.CYAN_1)
    draw_text(canvas, HUD_WIDTH - font.text_width(state.run_clock) - 2, TITLE_BAR_TOP,
              state.run_clock, palette.RIM)


def draw_hud(state=DEMO_STATE):
    """The whole 320x40 strip as an index array."""
    canvas = Canvas(HUD_WIDTH, HUD_HEIGHT, palette.VOID)
    _title_bar(canvas, state)
    _trace_panel(canvas, state)
    _integrity_panel(canvas, state)
    _cycles_panel(canvas, state)
    _token_panel(canvas, state)
    _weapon_panel(canvas, state)
    return canvas.array


def compose_screen(window_chunky, state=DEMO_STATE):
    """160x80 chunky render + HUD strip -> the full 320x200 the player sees."""
    if window_chunky.shape != (WINDOW_CHUNKY_HEIGHT, WINDOW_CHUNKY_WIDTH):
        raise ValueError("window must be %dx%d chunky pixels"
                         % (WINDOW_CHUNKY_WIDTH, WINDOW_CHUNKY_HEIGHT))
    screen = np.full((SCREEN_HEIGHT, SCREEN_WIDTH), palette.VOID, dtype=np.uint8)
    screen[:WINDOW_HEIGHT] = drawlib.upscale(window_chunky, PIXEL_DOUBLE)
    screen[HUD_TOP:] = draw_hud(state)
    return screen


PANELS = (("TRACE", TRACE_PANEL), ("INTEGRITY", INTEGRITY_PANEL), (CYCLES_LABEL, CYCLES_PANEL),
          ("KEY", TOKEN_PANEL), ("weapon icon", WEAPON_PANEL))
LABEL_INSET = 4


def label_overflows():
    """Panels whose own label does not fit inside them at the font's real advance."""
    return [(name, panel, font.text_width(name) + LABEL_INSET - (panel.x1 - panel.x0 + 1))
            for name, panel in PANELS
            if name.isupper() and font.text_width(name) + LABEL_INSET > panel.x1 - panel.x0 + 1]


def main():
    pixelio.ensure_dirs()
    array = draw_hud()
    pixelio.save(array, "hud_strip")
    planar_bytes = HUD_WIDTH // 2 * HUD_HEIGHT
    print("HUD strip %dx%d = %d chunky bytes, %d planar bytes (4 bitplanes)"
          % (HUD_WIDTH, HUD_HEIGHT, array.size, planar_bytes))
    print("render window %dx%d chunky -> %dx%d doubled; c2p emits %d planar bytes/frame"
          % (WINDOW_CHUNKY_WIDTH, WINDOW_CHUNKY_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT,
             WINDOW_WIDTH // 2 * WINDOW_HEIGHT))
    print("indices used: %s" % ",".join(str(i) for i in drawlib.indices_used(array)))
    overflows = label_overflows()
    print("font: %d glyphs, advance %d, %d bytes on target; panel labels overflowing: %s"
          % (font.GLYPH_COUNT, font.ADVANCE, font.FONT_BYTES,
             ", ".join("%s by %dpx" % (name, over) for name, _, over in overflows) or "none"))
    return 1 if overflows else 0


if __name__ == "__main__":
    raise SystemExit(main())
