"""BLACK ICE sprites - 4 enemies, 4 pickups, 2 weapons (idle + firing) and a data particle.

Everything here is indexed art with TRANSPARENT_INDEX meaning "do not draw".  The engine
draws one view per enemy: these are front-facing billboards, so the silhouette does all the
work and every enemy must be recognisable by outline alone at a quarter of its native size.

The rule that makes them readable on ANY wall at ANY depth: a 1-px white (RIM) outline, laid
down by `drawlib.apply_rim` after the body is finished.  White is wall-forbidden, so the rim
can never be camouflaged.  ALERT orange is the other wall-forbidden colour and is used only
for the live core of a thing that can hurt you - eye, iris, muzzle, thruster.

Enemies are bilaterally symmetric, so each is drawn in its left half and mirrored: symmetry
by construction beats symmetry by hand, and it halves the coordinates a reader has to check.
"""

import contextlib
import math

import numpy as np

import drawlib
import palette
import pixelio
from drawlib import Canvas

ENEMY_SIZE = 64
ENEMY_MAX = ENEMY_SIZE - 1
#: The mirror axis sits between columns 31 and 32; asymmetric detail must live left of it.
MIRROR_AXIS = ENEMY_SIZE // 2
PICKUP_SIZE = 32
PARTICLE_SIZE = 16
#: The weapon is drawn into the chunky buffer at the bottom centre of the 160x80 window.
WEAPON_WIDTH, WEAPON_HEIGHT = 96, 48
KEY = palette.TRANSPARENT_INDEX
RECOIL_KICK = 3

#: Sprite canvases are normally filled with the key.  `probe_ground` swaps it for a colour no
#: builder paints, so `key_leaks` can tell "transparent" from "painted slate" - the two are
#: indistinguishable once a sprite has been built the normal way.
PROBE_GROUND = palette.VOID
_canvas_ground = KEY


@contextlib.contextmanager
def probe_ground(ground=PROBE_GROUND):
    """Build sprites on a non-key ground, for the key-leak gate only."""
    global _canvas_ground
    previous, _canvas_ground = _canvas_ground, ground
    try:
        yield
    finally:
        _canvas_ground = previous


def _enemy_canvas():
    return Canvas(ENEMY_SIZE, ENEMY_SIZE, _canvas_ground)


def _finish(canvas, mirror=True):
    """Mirror (if symmetric) then lay the rim-light down - always the last operation."""
    array = drawlib.mirror_left_half(canvas.array) if mirror else canvas.array
    return drawlib.apply_rim(array, KEY, palette.RIM)


# --- enemies ---------------------------------------------------------------------------------


def watchdog():
    """Packs of four, walks straight at you.  Low, wide, four splayed legs - a floor shape."""
    canvas = _enemy_canvas()
    canvas.polygon([(13, 32), (21, 32), (16, 57), (9, 57)], palette.MAG_5)           # rear leg
    canvas.polygon([(6, 22), (14, 13), (31, 13), (31, 40), (10, 40)], palette.MAG_3) # chassis
    canvas.polygon([(6, 22), (14, 13), (31, 13), (31, 16), (15, 16), (9, 23)], palette.MAG_1)
    canvas.polygon([(6, 36), (10, 36), (10, 40), (6, 40)], palette.MAG_4)
    canvas.polygon([(14, 19), (31, 19), (31, 39), (17, 37)], palette.MAG_4)          # snout
    canvas.polygon([(10, 37), (19, 37), (10, 61), (1, 61)], palette.MAG_4)           # front leg
    canvas.polygon([(10, 37), (14, 37), (5, 61), (1, 61)], palette.MAG_2)
    canvas.rect(15, 23, 31, 32, palette.MAG_5)                                       # eye housing
    canvas.rect(17, 25, 31, 30, palette.ALERT)
    canvas.rect(17, 25, 31, 26, palette.RIM)
    canvas.polygon([(19, 38), (26, 38), (25, 51), (20, 49)], palette.MAG_2)          # zap prong
    canvas.rect(21, 46, 25, 51, palette.ALERT)
    canvas.polygon([(22, 3), (28, 3), (29, 13), (23, 13)], palette.MAG_3)            # sensor spike
    canvas.rect(22, 3, 28, 6, palette.ALERT)
    return _finish(canvas)


def sentry():
    """A turret in the wall.  Only the open iris can be hurt, so the iris is the whole design."""
    canvas = _enemy_canvas()
    for outer_y, inner_y in ((2, 13), (61, 50)):                          # wall mounting lugs
        inward = 1 if inner_y > outer_y else -1
        canvas.polygon([(5, outer_y), (31, outer_y), (31, inner_y), (11, inner_y)], palette.MAG_4)
        canvas.polygon([(5, outer_y), (31, outer_y), (31, outer_y + 3 * inward),
                        (7, outer_y + 3 * inward)], palette.MAG_2)
    canvas.polygon([(1, 15), (15, 1), (48, 1), (62, 15), (62, 48), (48, 62), (15, 62), (1, 48)],
                   palette.MAG_5)
    canvas.polygon([(5, 17), (17, 5), (46, 5), (58, 17), (58, 46), (46, 58), (17, 58), (5, 46)],
                   palette.MAG_4)
    canvas.polygon([(5, 17), (17, 5), (46, 5), (46, 8), (18, 8), (8, 18)], palette.MAG_2)
    canvas.ellipse(8, 8, 55, 55, palette.MAG_3)
    canvas.ellipse(11, 11, 52, 52, palette.MAG_5)
    _iris(canvas, MIRROR_AXIS, MIRROR_AXIS, aperture=9, reach=20)
    canvas.ellipse(24, 24, 39, 39, palette.MAG_5)
    canvas.ellipse(26, 26, 37, 37, palette.ALERT)
    canvas.ellipse(29, 29, 34, 34, palette.RIM)
    for bolt_x, bolt_y in ((6, 6), (6, 52), (16, 16)):
        canvas.rect(bolt_x, bolt_y, bolt_x + 5, bolt_y + 5, palette.MAG_1)
        canvas.rect(bolt_x + 2, bolt_y + 2, bolt_x + 3, bolt_y + 3, palette.MAG_5)
    return _finish(canvas)


IRIS_BLADES = 6


def _iris(canvas, cx, cy, aperture, reach):
    """Six shutter blades around a central hole - the tell that the Sentry is firing."""
    for blade in range(IRIS_BLADES):
        angle = 2.0 * np.pi * blade / IRIS_BLADES
        step = 2.0 * np.pi / IRIS_BLADES
        tip = (cx + reach * np.cos(angle), cy + reach * np.sin(angle))
        root_a = (cx + aperture * np.cos(angle - step / 2), cy + aperture * np.sin(angle - step / 2))
        root_b = (cx + aperture * np.cos(angle + step / 2), cy + aperture * np.sin(angle + step / 2))
        canvas.polygon([tip, root_a, root_b], palette.MAG_2 if blade % 2 else palette.MAG_3)


def tracer():
    """Fast, strafes, runs for the alarm.  A swept dart - the widest silhouette of the four."""
    canvas = _enemy_canvas()
    canvas.polygon([(1, 24), (27, 20), (30, 31), (6, 36)], palette.MAG_4)            # wing
    canvas.polygon([(1, 24), (27, 20), (28, 24), (3, 29)], palette.MAG_1)            # leading edge
    canvas.polygon([(5, 33), (17, 30), (18, 41), (6, 43)], palette.MAG_5)            # engine pod
    canvas.rect(6, 36, 11, 41, palette.ALERT)
    canvas.polygon([(21, 10), (31, 3), (31, 51), (23, 45)], palette.MAG_3)           # fuselage
    canvas.polygon([(21, 10), (31, 3), (31, 8), (23, 15)], palette.MAG_1)
    canvas.polygon([(24, 15), (31, 11), (31, 26), (25, 23)], palette.ALERT)          # sensor lens
    canvas.polygon([(27, 17), (31, 14), (31, 20), (28, 19)], palette.RIM)
    canvas.polygon([(24, 45), (31, 41), (31, 61), (26, 55)], palette.MAG_5)          # tail fin
    return _finish(canvas)


def black_ice():
    """The boss.  A tall shard figure that mirrors you - so it is drawn mirror-perfect."""
    canvas = _enemy_canvas()
    canvas.polygon([(17, 43), (31, 39), (31, 62), (13, 62)], palette.MAG_5)          # column
    canvas.polygon([(24, 43), (31, 41), (31, 62), (24, 62)], palette.MAG_4)
    canvas.polygon([(12, 21), (31, 13), (31, 48), (16, 45)], palette.MAG_4)          # torso
    canvas.polygon([(12, 21), (31, 13), (31, 19), (15, 27)], palette.MAG_2)
    canvas.polygon([(2, 20), (18, 14), (21, 27), (5, 33)], palette.MAG_3)            # shoulder shard
    canvas.polygon([(2, 20), (18, 14), (18, 18), (4, 24)], palette.MAG_1)
    canvas.polygon([(1, 25), (10, 29), (9, 53), (2, 47)], palette.MAG_5)             # arm shard
    canvas.polygon([(1, 25), (5, 27), (4, 49), (2, 47)], palette.MAG_1)
    canvas.polygon([(19, 9), (31, 2), (31, 23), (20, 17)], palette.MAG_3)           # head shard
    canvas.polygon([(22, 9), (31, 4), (31, 20), (23, 15)], palette.MAG_5)
    canvas.rect(24, 9, 31, 13, palette.ALERT)                                        # eye slit
    canvas.rect(24, 9, 31, 10, palette.RIM)
    canvas.polygon([(23, 27), (31, 22), (31, 40), (23, 35)], palette.MAG_2)          # chest core
    canvas.polygon([(26, 28), (31, 25), (31, 37), (26, 34)], palette.ALERT)
    canvas.polygon([(29, 29), (31, 28), (31, 34), (29, 33)], palette.RIM)
    return _finish(canvas)


ENEMY_BUILDERS = (
    ("watchdog", watchdog),
    ("sentry", sentry),
    ("tracer", tracer),
    ("black_ice", black_ice),
)


# --- pickups ---------------------------------------------------------------------------------


def _pickup_canvas():
    return Canvas(PICKUP_SIZE, PICKUP_SIZE, _canvas_ground)


def _finish_pickup(canvas):
    return drawlib.apply_rim(canvas.array, KEY, palette.RIM)


def cycles_cell():
    """Ammo.  A charge cell: cyan casing, three yellow charge bars, a contact cap."""
    canvas = _pickup_canvas()
    canvas.rect(6, 4, 25, 29, palette.CYAN_5)
    canvas.rect(6, 4, 25, 6, palette.CYAN_2)
    canvas.rect(6, 4, 8, 29, palette.CYAN_2)
    canvas.rect(23, 4, 25, 29, palette.CYAN_4)
    canvas.rect(11, 1, 20, 5, palette.CYAN_2)
    for bar in range(3):
        bar_y = 9 + bar * 7
        canvas.rect(10, bar_y, 21, bar_y + 4, palette.CYAN_1)
    return _finish_pickup(canvas)


def integrity_patch():
    """Health.  A square repair plate - deliberately NOT the Sentry's octagon, because a distant
    heal and a distant turret sharing a silhouette is a fatal read."""
    canvas = _pickup_canvas()
    canvas.rect(3, 5, 28, 26, palette.CYAN_5)
    canvas.rect(5, 7, 26, 24, palette.INTEGRITY)
    canvas.rect(13, 8, 18, 23, palette.RIM)
    canvas.rect(7, 13, 24, 18, palette.RIM)
    for rivet_x in (5, 24):
        for rivet_y in (7, 22):
            canvas.rect(rivet_x, rivet_y, rivet_x + 2, rivet_y + 2, palette.CYAN_2)
    return _finish_pickup(canvas)


def access_token():
    """One of the three keys out.  A wedge card: shape says 'this goes in a slot'."""
    canvas = _pickup_canvas()
    canvas.polygon([(3, 7), (21, 7), (28, 15), (21, 24), (3, 24)], palette.DATA)
    canvas.polygon([(3, 7), (21, 7), (23, 9), (3, 9)], palette.RIM)
    canvas.rect(6, 12, 15, 14, palette.CYAN_5)
    canvas.rect(6, 17, 12, 19, palette.CYAN_5)
    canvas.rect(18, 12, 21, 19, palette.CYAN_3)
    return _finish_pickup(canvas)


def trace_scrubber():
    """Lowers the trace meter.  A cable cut clean through, with the magenta trace it was
    carrying stopping dead at the break.  The old icon needed a legend; this one does not."""
    canvas = _pickup_canvas()
    canvas.rect(2, 4, 29, 27, palette.CYAN_5)
    canvas.rect(2, 4, 29, 6, palette.CYAN_2)
    canvas.rect(2, 10, 12, 19, palette.CYAN_3)                    # cable, left of the break
    canvas.rect(2, 10, 12, 12, palette.CYAN_1)
    canvas.rect(19, 13, 29, 22, palette.CYAN_3)                   # right end, pulled out of line
    canvas.rect(19, 13, 29, 15, palette.CYAN_1)
    canvas.rect(2, 21, 11, 24, palette.MAG_2)                     # the trace it was carrying
    canvas.polygon([(12, 9), (17, 14), (12, 20)], palette.RIM)                 # cut ends, sheared
    canvas.polygon([(20, 12), (15, 18), (20, 23)], palette.RIM)
    canvas.rect(15, 15, 17, 17, palette.RIM)                      # the spark across the break
    return _finish_pickup(canvas)


PICKUP_BUILDERS = (
    ("cycles_cell", cycles_cell),
    ("integrity_patch", integrity_patch),
    ("access_token", access_token),
    ("trace_scrubber", trace_scrubber),
)


# --- weapons ---------------------------------------------------------------------------------


def _weapon_canvas():
    return Canvas(WEAPON_WIDTH, WEAPON_HEIGHT, _canvas_ground)


#: The window is 80 rows.  Idle live art starts no higher than this row of the overlay, which
#: puts it in the bottom 36 rows of the window: a 25-row enemy centred on the horizon spans
#: window rows 28-52, so a weapon that starts higher is standing in front of what you shoot at.
WEAPON_IDLE_TOP_ROW = 12
#: A muzzle burst may climb this many rows above that, and no further.
WEAPON_BURST_HEADROOM = 12
#: A held gun is asymmetric: the wrist enters at the bottom-right corner and the barrel angles
#: up and to the left.  A weapon centred on the window reads as furniture, not as a hand.
WRIST_ORIGIN = (WEAPON_WIDTH + 4, WEAPON_HEIGHT + 4)
BUSTER_GRIP, BUSTER_MUZZLE = (84, 45), (54, 21)
SPIKE_GRIP, SPIKE_MUZZLE = (86, 46), (52, 23)


def _axis_vectors(origin, tip):
    """(along, across) unit vectors of the origin->tip axis; `across` points to the lit side."""
    run_x, run_y = tip[0] - origin[0], tip[1] - origin[1]
    length = math.hypot(run_x, run_y)
    return (run_x / length, run_y / length), (-run_y / length, run_x / length)


def _slab(origin, tip, half_width):
    """Corners of a rectangle of 2*half_width laid along the origin->tip axis."""
    _, across = _axis_vectors(origin, tip)
    offset_x, offset_y = across[0] * half_width, across[1] * half_width
    return [(origin[0] + offset_x, origin[1] + offset_y), (tip[0] + offset_x, tip[1] + offset_y),
            (tip[0] - offset_x, tip[1] - offset_y), (origin[0] - offset_x, origin[1] - offset_y)]


def _point_on(origin, tip, fraction, sideways=0.0):
    """A point `fraction` of the way along the axis, pushed `sideways` off it."""
    _, across = _axis_vectors(origin, tip)
    return (origin[0] + (tip[0] - origin[0]) * fraction + across[0] * sideways,
            origin[1] + (tip[1] - origin[1]) * fraction + across[1] * sideways)


def _rail(canvas, origin, tip, from_fraction, to_fraction, sideways, half_width, ink):
    """A slab running along part of the gun's axis - the whole frame is built from these."""
    canvas.polygon(_slab(_point_on(origin, tip, from_fraction, sideways),
                         _point_on(origin, tip, to_fraction, sideways), half_width), ink)


def _fin(canvas, origin, tip, fraction, span, thickness, ink):
    """A cooling fin ACROSS the barrel - the one detail that breaks a tube into a weapon."""
    canvas.polygon(_slab(_point_on(origin, tip, fraction, span),
                         _point_on(origin, tip, fraction, -span), thickness), ink)


def _lower(point, drop):
    return (point[0], point[1] + drop)


def _fist(canvas, centre, drop, radius):
    """The runner's hand on the grip: a dark glove, a lit knuckle band, three finger grooves.

    Deep cyan and not slate: slate IS the transparency key, so a slate glove is a hole.
    """
    x, y = centre[0], centre[1] + drop
    canvas.ellipse(x - radius, y - radius, x + radius, y + radius, palette.CYAN_5)
    canvas.rect(x - radius + 1, y - radius + 3, x + radius - 1, y + 2, palette.CYAN_4)
    canvas.rect(x - radius + 1, y - radius + 3, x + radius - 1, y - radius + 5, palette.CYAN_2)
    for finger in range(3):
        groove_y = y - radius + 7 + finger * 4
        canvas.rect(x - radius + 2, groove_y, x + radius - 2, groove_y + 1, palette.CYAN_5)


def _emitter(canvas, centre, drop, radius_x, radius_y, bore_ink):
    """The muzzle seen almost head-on: a flared ring with a bore you can look down."""
    x, y = centre[0], centre[1] + drop
    canvas.ellipse(x - radius_x, y - radius_y, x + radius_x, y + radius_y, palette.CYAN_3)
    canvas.ellipse(x - radius_x, y - radius_y, x + radius_x, y - radius_y + 3, palette.CYAN_1)
    canvas.ellipse(x - radius_x + 4, y - radius_y + 3, x + radius_x - 4, y + radius_y - 3,
                   palette.CYAN_5)
    canvas.ellipse(x - radius_x + 7, y - radius_y + 5, x + radius_x - 7, y + radius_y - 5,
                   bore_ink)


def _buster_body(canvas, drop):
    """Buster: fast, weak, infinite floor.  A light frame held up and across the body."""
    grip, muzzle = _lower(BUSTER_GRIP, drop), _lower(BUSTER_MUZZLE, drop)
    canvas.polygon(_slab(_lower(WRIST_ORIGIN, drop), grip, 10), palette.CYAN_5)
    _rail(canvas, grip, muzzle, 0.00, 0.50, 0, 11, palette.CYAN_4)          # receiver
    _rail(canvas, grip, muzzle, 0.35, 1.00, 0, 7, palette.CYAN_4)           # barrel
    _rail(canvas, grip, muzzle, 0.00, 0.50, -8, 3, palette.CYAN_2)          # lit receiver edge
    _rail(canvas, grip, muzzle, 0.35, 1.00, -4, 2, palette.CYAN_2)          # lit barrel edge
    _rail(canvas, grip, muzzle, 0.00, 0.50, 8, 3, palette.CYAN_5)           # shadow side
    _rail(canvas, grip, muzzle, 0.35, 1.00, 4, 2, palette.CYAN_5)
    _rail(canvas, grip, muzzle, 0.42, 0.92, 0, 2, palette.CYAN_5)           # sight rib
    _rail(canvas, grip, muzzle, 0.08, 0.24, -4, 4, palette.CYAN_1)          # charge readout
    _fin(canvas, grip, muzzle, 0.52, 9, 2, palette.CYAN_5)
    _fist(canvas, BUSTER_GRIP, drop, radius=11)
    _emitter(canvas, BUSTER_MUZZLE, drop, radius_x=13, radius_y=8, bore_ink=palette.CYAN_1)


def _spike_body(canvas, drop):
    """Spike: slow, pierces a whole corridor.  Heavier, and the magenta rail says why."""
    grip, muzzle = _lower(SPIKE_GRIP, drop), _lower(SPIKE_MUZZLE, drop)
    canvas.polygon(_slab(_lower(WRIST_ORIGIN, drop), grip, 12), palette.CYAN_5)
    _rail(canvas, grip, muzzle, 0.00, 0.55, 0, 14, palette.CYAN_4)          # receiver
    _rail(canvas, grip, muzzle, 0.40, 1.00, 0, 9, palette.CYAN_4)           # barrel
    _rail(canvas, grip, muzzle, 0.00, 0.55, -10, 4, palette.CYAN_2)
    _rail(canvas, grip, muzzle, 0.40, 1.00, -6, 3, palette.CYAN_2)
    _rail(canvas, grip, muzzle, 0.00, 0.55, 10, 4, palette.CYAN_5)
    _rail(canvas, grip, muzzle, 0.40, 1.00, 6, 3, palette.CYAN_5)
    _rail(canvas, grip, muzzle, 0.10, 1.00, 0, 5, palette.MAG_4)            # accelerator rail
    _rail(canvas, grip, muzzle, 0.10, 1.00, 0, 3, palette.MAG_2)
    _rail(canvas, grip, muzzle, 0.20, 0.95, -1, 1, palette.MAG_1)
    for fraction in (0.46, 0.60, 0.74):
        _fin(canvas, grip, muzzle, fraction, 11, 2, palette.CYAN_5)
    _fist(canvas, SPIKE_GRIP, drop, radius=13)
    _emitter(canvas, SPIKE_MUZZLE, drop, radius_x=17, radius_y=9, bore_ink=palette.MAG_2)


def buster_idle():
    canvas = _weapon_canvas()
    _buster_body(canvas, drop=0)
    return canvas.array


def buster_firing():
    canvas = _weapon_canvas()
    _buster_body(canvas, drop=RECOIL_KICK)
    _muzzle_flash(canvas, _lower(BUSTER_MUZZLE, RECOIL_KICK), reach=14, core=palette.CYAN_1)
    return canvas.array


def spike_idle():
    canvas = _weapon_canvas()
    _spike_body(canvas, drop=0)
    return canvas.array


def spike_firing():
    canvas = _weapon_canvas()
    _spike_body(canvas, drop=RECOIL_KICK)
    _muzzle_flash(canvas, _lower(SPIKE_MUZZLE, RECOIL_KICK), reach=18, core=palette.MAG_1)
    return canvas.array


FLASH_SPOKES = 10


def _muzzle_flash(canvas, centre, reach, core):
    """A hot star at the bore: white heart, orange body, coloured spokes.  Both are reserved."""
    centre_x, centre_y = centre
    for spoke in range(FLASH_SPOKES):
        angle = 2.0 * math.pi * spoke / FLASH_SPOKES
        length = reach if spoke % 2 else reach * 3 // 5
        tip = (centre_x + length * math.cos(angle), centre_y + length * math.sin(angle))
        canvas.polyline([(centre_x, centre_y), tip], core, width=4)
    canvas.ellipse(centre_x - 8, centre_y - 6, centre_x + 8, centre_y + 6, core)
    canvas.ellipse(centre_x - 5, centre_y - 4, centre_x + 5, centre_y + 4, palette.ALERT)
    canvas.ellipse(centre_x - 3, centre_y - 2, centre_x + 3, centre_y + 2, palette.RIM)


WEAPON_BUILDERS = (
    ("buster_idle", buster_idle),
    ("buster_firing", buster_firing),
    ("spike_idle", spike_idle),
    ("spike_firing", spike_firing),
)


# --- particle --------------------------------------------------------------------------------


def data_particle():
    """What an enemy or a crate leaves behind: a fragment of data, four spokes and a core."""
    canvas = Canvas(PARTICLE_SIZE, PARTICLE_SIZE, _canvas_ground)
    centre = PARTICLE_SIZE // 2
    canvas.rect(centre - 1, 1, centre, PARTICLE_SIZE - 2, palette.DATA)
    canvas.rect(1, centre - 1, PARTICLE_SIZE - 2, centre, palette.DATA)
    canvas.rect(centre - 3, centre - 3, centre + 2, centre + 2, palette.DATA)
    canvas.rect(centre - 2, centre - 2, centre + 1, centre + 1, palette.RIM)
    return canvas.array


# --- registry and ledger -----------------------------------------------------------------------
ALL_BUILDERS = ENEMY_BUILDERS + PICKUP_BUILDERS + WEAPON_BUILDERS + (("data_particle", data_particle),)


def build_all():
    return {name: builder() for name, builder in ALL_BUILDERS}


def enemies():
    return {name: builder() for name, builder in ENEMY_BUILDERS}


def rim_pixel_count(array):
    return int((array == palette.RIM).sum())


def rimmed_names():
    """Every sprite that must carry a rim: the enemies and the pickups."""
    return [name for name, _ in ENEMY_BUILDERS + PICKUP_BUILDERS]


def unrimmed_halo_pixels(array):
    """Halo pixels around the silhouette that are not RIM.  Must be zero for a rimmed sprite.

    Two pickups shipped Revision 2 with no rim at all because they returned `canvas.array`
    instead of `_finish_pickup(canvas)`, and the old check - which only looked at the sprite's
    border rows - could not see it.  This one asserts the halo itself.
    """
    body = (array != KEY) & (array != palette.RIM)
    halo = drawlib.rim_mask(np.where(body, array, KEY), KEY)
    off_edge = int(((np.concatenate((array[0], array[-1], array[:, 0], array[:, -1]))
                     != KEY) & (np.concatenate((array[0], array[-1], array[:, 0],
                                                array[:, -1])) != palette.RIM)).sum())
    return int((array[halo] != palette.RIM).sum()) + off_edge


def key_leaks():
    """{name: painted pixels that came out equal to the key} - every entry must be empty.

    Built on a VOID ground: anything still equal to KEY afterwards was painted there by a
    builder reaching for slate, and on target it will be punched back out by the sprite blit.
    """
    with probe_ground():
        probes = {name: builder() for name, builder in ALL_BUILDERS}
    return {name: int((array == KEY).sum()) for name, array in probes.items()}


def ink_rows(array):
    """(first, last) rows of an overlay that actually paint - the weapon's real footprint."""
    rows = np.where((array != KEY).any(axis=1))[0]
    return (int(rows.min()), int(rows.max()))


def weapon_footprints():
    """[(name, first row, last row, allowed first row), ...] for the overlay gate."""
    built = build_all()
    rows = []
    for name, _ in WEAPON_BUILDERS:
        first, last = ink_rows(built[name])
        allowed = (WEAPON_IDLE_TOP_ROW - WEAPON_BURST_HEADROOM if name.endswith("firing")
                   else WEAPON_IDLE_TOP_ROW)
        rows.append((name, first, last, allowed))
    return rows


def main():
    pixelio.ensure_dirs()
    total = 0
    print("sprite            size      bytes  rim px  transparent px")
    for name, array in build_all().items():
        pixelio.save(array, "spr_" + name)
        total += array.size
        print("  %-16s %3dx%-3d %6d  %6d  %6d"
              % (name, array.shape[1], array.shape[0], array.size,
                 rim_pixel_count(array), int((array == KEY).sum())))
    print()
    print("weapon overlay footprint (window is %d rows; the overlay sits at its bottom)"
          % 80)
    overlay_ok = True
    for name, first, last, allowed in weapon_footprints():
        ok = first >= allowed
        overlay_ok = overlay_ok and ok
        print("  %-14s ink rows %2d..%2d = %2d rows, first row must be >= %2d  %s"
              % (name, first, last, last - first + 1, allowed, "ok" if ok else "TOO TALL"))
    built = build_all()
    print()
    print("rim + key gates")
    leaks = key_leaks()
    unrimmed = {name: unrimmed_halo_pixels(built[name]) for name in rimmed_names()}
    for name in sorted(set(leaks) | set(unrimmed)):
        print("  %-16s key pixels painted: %3d   unrimmed halo pixels: %s"
              % (name, leaks[name], unrimmed.get(name, "n/a")))
    enclosed = not any(unrimmed.values()) and not any(leaks.values())
    print("total %d sprites = %d bytes (byte per texel), %d bytes nibble-packed"
          % (len(ALL_BUILDERS), total, total // 2))
    print("every rimmed sprite fully rimmed and no sprite paints the key: %s"
          % ("YES" if enclosed else "NO"))
    return 0 if enclosed and overlay_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
