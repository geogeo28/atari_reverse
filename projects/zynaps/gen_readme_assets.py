#!/usr/bin/env python3
"""Render the workspace README's Zynaps images straight from the verified C reconstruction.

Every picture here is *drawn by the reconstruction*, not screenshotted from the original program.
`../../tools/recreate_kit` loads and relocates your own `bin/ZYNAPS17.PRG` into the flat image the
differential harness uses, and this script then calls the very same entry points `recreate/test/`
calls through ctypes — `recreate/src/init.c`'s boot and section slices, `recreate/src/frame.c`'s
`frame_loop_once`,
`recreate/src/hud.c`'s and `recreate/src/highscore.c`'s screens,
`recreate/src/sprite.c`'s masked blitter — and de-interleaves
the Atari low-resolution framebuffer they paint into a PNG. NO ORACLE RUNS HERE: `test_frame.py`
stages its worlds by stepping the ORIGINAL's machine code through Musashi, and this file
deliberately does not, because a picture drawn by the oracle would be a picture of the 1988 binary.

EVERY PICTURE OF A SECTION RUNS THE WHOLE BOOT AND SECTION CHAIN, in `zynaps_main.c`'s order,
which is `_start`'s. (The two front-end pages stop where the game does, at the attract loop, and
never enter the section chain at all.) That is not thoroughness for its own sake: the status panel
along the bottom of every play frame is drawn by no part of the frame loop. `boot_load_title_assets`
reads STATUS.PI1 and carves three strips out of it, `status_panel_build_master` composes the panel,
and `section_restart_prologue` — through `section_reload_intro_screens`, which it calls itself
(`recreate/src/init.c`) — stamps it into both framebuffers and flips, which is also what sets the
buffer parity every later picture is taken at. A section booted without the chain above it shows a
playfield over nothing, which looks plausible and is wrong.

WHAT THAT ORDER IS AND IS NOT EVIDENCE OF, since a reviewer asked. The chain here is the machine
build's, step for step, so nothing on the path is a shape this script invented. It is NOT the case
that every step is separately load-bearing for these pictures: `section_reload_intro_screens` is
called explicitly because `play_one_game` calls it explicitly, and removing that call leaves all
eleven PNGs byte-identical — measured — because the prologue after it makes the same call. The
on-target `gamefault` control drops the step from a run sampled at frames 1 to 240 and reddens every
one of them; that is a result about that build, not about this set, and it is not borrowed here.

Nothing here needs Hatari or a TOS ROM: the twenty-two files `_start` opens (eight for the title,
then fourteen more) and each section's own five to seven come through the kit's STAGED-FILE MODEL
(`harness.stage_files`, TRAP_MODEL.md's Phase 4)
instead of through GEMDOS, and the three busy-waits a boot and a frame contain — the section
start's wait for the fire button and the frame's wait for the raster and then for the vertical
blank, none of which any instruction of the game writes — are answered by the kit's SCHEDULED-WRITE
model (Phase 8) rather than by an interrupt. It does need YOUR OWN copy of the game under `bin/`
and a built candidate; no game code or data is distributed with this repository.

NEITHER THE PALETTE NOR THE BUFFER IS CHOSEN HERE, and the reason is the same for both: the two
registers that decide them — the sixteen colour words at $ff8240 and the screen base at
$ff8203/$ff8201 — are far above the 1 MiB image, so the image says what the CANDIDATES are and not
which one is in force. The rows a picture might take its palette from are ordinary memory and there
are four of them (`palette_boot`, `palette_frontend`, `palette_hw_shadow` and the row the menu VBL
uploads); both framebuffers are ordinary memory too, and one of them is a frame behind. Picking
wrong in either produces a picture that is plausible and wrong — measured, on the first draft of
this set, which rendered a level in the title screen's colours. So both are taken from what the
reconstruction actually STORED, through the kit's HARDWARE-WRITE LEDGER (Phase 10): the pens from
the upload made by `attract_build_colour_bars` or by the reconstruction's own `vbl_menu` run on a
COPY of the pictured state, and the screen base from whichever slice last flipped, which
`_the_buffer_the_shifter_is_showing` then requires to agree with `A_screen_front`.

TWO THINGS A FRAMEBUFFER CANNOT HOLD, said here rather than left to be noticed. The attract screen's
colour bars are painted by `attract_rasterbar_isr` one scanline at a time straight into pen 0, so
they exist only on a raster and not in any buffer — the title page below is the page they run
behind. And `frame_loop_once` takes two 68000 registers the loop carries across a verified callee's
`rts` (`recreate/include/frame.h`); off target `test_frame.py` reads them from the oracle at that PC, and
this script — like `recreate/atari/`'s on-target build, which has no oracle either — passes the same
zeros that build does, so these frames are the ones the playable `.PRG` would draw.

WHICH FRAME EACH PLAY PICTURE IS, IS SEARCHED FOR AND NOT TYPED — with one stated exception. A
section is played with one fixed joystick script (`test_frame.world_rng`'s stream, the suite's own,
so the worlds here and the worlds under `make test` are the same worlds), and `_play_until` keeps
the first frame whose census reaches a floor: so many live entity records, so many asteroids in
flight. The exception is `section1-start`, which is a picture of a MOMENT rather than of a state and
takes a stated frame number through `_play_exactly`. What the search buys is that a caption about
the SHAPE of a frame — busy, full of rocks — cannot outlive a change that shifts the run, because
the run refuses instead. What it does not buy is exactness: the census is a floor, so a caption
quoting a precise count is quoting today's run and not a guarantee, and the run prints every count
it kept so the next person can requote them.

Output goes to the tracked `<workspace>/assets/zynaps/*.png`, and every run is byte-identical: the
whole set is a function of `ZYNAPS17.PRG`, the game's own data files and that joystick script, and
nothing reads a clock. THAT IS ASSERTED AND NOT CLAIMED — `main` renders the whole set TWICE and
refuses a picture whose two renderings differ. Re-run:

    cd recreate && make venv && make test   # once: the venv, libzynaps.so AND liboracle.so, which
                                           # `harness` dlopens at import even though nothing here
                                           # runs the oracle (`make` alone builds only the candidate)
    ./.venv/bin/python ../gen_readme_assets.py
"""
import ctypes
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
RECREATE = HERE / "recreate"
sys.path.insert(0, str(WORKSPACE / "tools"))     # write_png
sys.path.insert(0, str(RECREATE / "test"))       # harness.py — binds the kit and loads the .so

import harness                     # noqa: E402  loads ZYNAPS17.PRG into the image, opens libzynaps.so
import emu                         # noqa: E402  the schedule encoder both shores share (harness put
                                   #             it on sys.path); no oracle is RUN here
import test_init as boot           # noqa: E402  the boot/section slices, and their file lists
import test_frame as frame         # noqa: E402  the frame loop, the entity record, the joystick
import test_hud as hud             # noqa: E402  the two framebuffer pointers
import test_video as video         # noqa: E402  the screen geometry and the shifter's colour row
import test_sprite as sprite       # noqa: E402  the masked sprite's row geometry
import st_pixels                   # noqa: E402  the workspace's ONE ST plane/palette model
from extract_graphics import write_png             # noqa: E402

# The two names this script borrows from `test_init` that are UNDERSCORE-PRIVATE, checked at import
# so a rename over there fails HERE with a sentence instead of an `AttributeError` several pictures
# into a run that has already overwritten half the tracked set. `test_frame.py` has the same guard
# over the same module for the same reason, and this file is a second borrower of one of them.
for _borrowed in ("_section_files", "_vsync_release"):
    assert hasattr(boot, _borrowed), (
        f"this script drives the boot and section chains through test_init.{_borrowed}; that name "
        f"is gone, so either restore it or give this script its own")

OUT = WORKSPACE / "assets" / "zynaps"
DISK = harness.PRG.parent / "disk"
LIB = harness._lib

# The three glues this script calls that NO imported battery binds (they are `test_irq`'s and
# `test_highscore`'s, and neither is imported here). Stated rather than left to ctypes' int-argument
# default, which would pass a 64-bit pointer as an `int` on the way in. `g_playfield_clear` and
# `g_draw_sprite_masked` are deliberately NOT in this list: `test_video` and `test_sprite` bind them
# above, and re-binding them here would silently overrule whatever those batteries later declare.
_IMAGE = ctypes.POINTER(ctypes.c_uint8)
for _glue in ("g_vbl_menu", "g_role_of_honour_screen", "g_game_over_screen_prologue"):
    getattr(LIB, _glue).argtypes = [_IMAGE]
    getattr(LIB, _glue).restype = None

# ---- the ST low-resolution framebuffer ------------------------------------------------------------
#
# The plane model, the `$0RGB` expansion and the row stride are `../../tools/st_pixels.py`'s — the
# workspace's one decoder — so nothing about the ST's pixels is spelt again here. Only the SHAPE of
# this game's screen is local, and both figures come out of the two `test_video` pins.
SCREEN_WIDTH = video.SCREEN_ROW_BYTES // st_pixels.group_bytes() * st_pixels.PIXELS_PER_WORD
SCREEN_HEIGHT = video.SCREEN_BYTES // video.SCREEN_ROW_BYTES

# ---- what a picture is made of -------------------------------------------------------------------
#
# The joystick stream is `test_frame`'s own, so a world here is a world the suite also builds; the
# frame kept is the first that meets the picture's census, and the run refuses to publish one that
# never does.
PLAY_FRAMES = 400                # a bound on the search, not a length: every picture stops earlier
FRAME_EXIT_NEXT_FRAME = frame.FRAME_EXIT_CODE[frame.STOP_FRAME]

# The section flow reaches section n by playing the n before it; `_stage_section` therefore puts the
# counter one short and lets `section_advance` do its own arithmetic.
SECTION_OPENER = 0               # `level_section` 0 — the section the game itself starts at
# The first of the four sections whose type byte is 'q': an asteroid field with no map at all. Taken
# from the binary's own table rather than typed, so a picture cannot be captioned "the asteroid
# field" over a section that has a map.
SECTION_ASTEROIDS = boot.ASTEROID_SECTIONS[0]
# Two later sections, picked by rendering all sixteen through this same script and keeping the two
# that look least like section 0's blue-grey lattice: 8 is a magenta cloud field over open space,
# and 11 is a jade cavern with a tiled ceiling as well as a floor — a different TILE SET and not
# only a different palette.
SECTION_MAGENTA = 8
SECTION_CAVERN = 11

# A picture's census: how many records must be live before a frame is kept. The two counts are
# `test_frame`'s and `test_init`'s, which `test_constants.py` pins to their headers, so "busy" here
# counts the same records `recreate/atari/census.py` and the bench count. Both are floors the run
# SEARCHES for; `_play_until` refuses one the section start already meets.
BUSY_ENTITIES = 10               # of `frame.ENTITY_SLOTS`, in sections 1, 9 and 12 — measured
BUSY_ROCKS = 12                  # of `boot.SECTION_RESTART_ASTEROID_RECORDS`, in section 2

# The opening frame: far enough in that the scroller has moved and the ship's exhaust is drawn,
# early enough that nothing has spawned yet. It is a stated number rather than a census because
# "the start" is what the picture is of.
OPENING_FRAME = 8


def _u32(image, at):
    return int.from_bytes(image[at:at + 4], "big")


# ==================================================================================================
# The screen: what the reconstruction painted, and what it published to the shifter
# ==================================================================================================

def _hardware_writes():
    """The run's ordered (address, width, value) hardware stores, out of the kit's WRITE ledger.

    The same three parallel arrays `harness.differential` compares entry for entry — the kit keeps
    no public decoded view of them, so this is a second reader rather than a second ledger.
    """
    count = LIB.g_hw_write_count()
    assert count < harness.OS_HW_WRITE_LOG_MAX, (
        f"the run made {count} hardware stores and the ledger caps at "
        f"{harness.OS_HW_WRITE_LOG_MAX} — what it holds is a truncated prefix, so nothing read out "
        f"of it here means what it says")
    addrs, widths, values = LIB.g_hw_write_addrs(), LIB.g_hw_write_widths(), LIB.g_hw_write_vals()
    return [(addrs[entry], widths[entry], values[entry]) for entry in range(count)]


def _pens_the_run_published():
    """The sixteen colour words the CANDIDATE just wrote to $ff8240, as RGB triples for the PNG.

    WHY THE LEDGER AND NOT A ROW. The palette a picture needs IS readable out of the image — the
    shadow rows the two uploaders copy from are ordinary memory. What is not readable is WHICH of
    them is in force: the image carries four sixteen-pen rows (`palette_boot` 0x19618,
    `palette_frontend` 0x195f8, `palette_hw_shadow` 0x18fc4 and `A_menu_palette` 0x19f46), the
    shifter registers that decide between them are far above the 1 MiB image, and picking the wrong
    one produces a picture that is plausible and wrong — measured, on the first draft of this set,
    which rendered a level in the title screen's colours. So the palette is taken from what the
    reconstruction actually STORED to $ff8240 rather than from a row this script nominated.

    THE PARSE IS TOTAL, not lenient: a store into the colour block of a width neither uploader makes
    is a refusal rather than a silently dropped entry, because a partly-parsed row would come back
    as "the run published fewer than sixteen pens" and send the reader after the wrong routine.
    """
    row_bytes = video.PALETTE_PENS * video.PALETTE_PEN_BYTES
    pens = {}
    for address, width, value in _hardware_writes():
        if not video.HW_PALETTE_BASE <= address < video.HW_PALETTE_BASE + row_bytes:
            continue
        pen = (address - video.HW_PALETTE_BASE) // video.PALETTE_PEN_BYTES
        if width == video.PALETTE_LONG_BYTES:      # `movem.l` — two pens at a time
            pens[pen] = (value >> 16) & 0xffff
            pens[pen + 1] = value & 0xffff
        elif width == video.PALETTE_PEN_BYTES:
            pens[pen] = value & 0xffff
        else:
            raise AssertionError(
                f"the run stored {width} byte(s) at {address:#x}, inside the colour block, and "
                f"neither `shifter_upload_palette_longs` nor `shifter_write_pen` makes a store that "
                f"width — this parser would drop it and report a short palette")
    assert sorted(pens) == list(range(video.PALETTE_PENS)), (
        f"the run published pens {sorted(pens)} of {video.PALETTE_PENS}, so the picture has no "
        f"palette of its own — the slice that uploads one did not run in this armed window")
    return st_pixels.palette_rgb([pens[pen] for pen in range(video.PALETTE_PENS)])


# THE SHIFTER, ACROSS A WHOLE RUN. The kit's write ledger is reset every time a candidate is armed,
# which is once per slice and once per frame, so no single ledger holds "what the screen is showing":
# a flip made by `player_intro_screen` is still on the shifter three slices later. `_note_the_publish`
# is called after every armed run and keeps the last base any of them stored — the machine's own
# behaviour, modelled rather than assumed.
#
# ONE RUN IS IN FLIGHT AT A TIME, which is why this is a module global rather than a field: every
# render below stages an image, uses it and drops it before the next one starts, and `_staged_image`
# is the single place a new run begins. The stream below it is per-run for the same reason.
_SHOWN_BASE = None
_PUBLISHES = 0
_STREAM = None


def _begin_a_run():
    """Forget the previous picture's shifter state and joystick stream."""
    global _SHOWN_BASE, _PUBLISHES, _STREAM
    _SHOWN_BASE, _PUBLISHES, _STREAM = None, 0, frame.world_rng()


def _note_the_publish():
    """Remember the screen base this armed run stored to the shifter, if it stored one.

    An STF's base register has no low byte: the original writes bits 15..8 to $ff8203 and 23..16 to
    $ff8201, in that order (include/video.h), so the address is those two bytes shifted back.
    """
    global _SHOWN_BASE, _PUBLISHES
    base = {}
    for address, _width, value in _hardware_writes():
        if address == video.HW_SCREEN_BASE_MID:
            base["mid"] = value & 0xff
        elif address == video.HW_SCREEN_BASE_HIGH:
            base["high"] = value & 0xff
    if len(base) == 2:
        _SHOWN_BASE = (base["high"] << 16) | (base["mid"] << 8)
        _PUBLISHES += 1


def _the_buffer_the_shifter_is_showing(image):
    """`A_screen_front`, CHECKED against the last screen base the run actually published.

    `screen_flip_buffers` swaps the two pointers and then writes the new one to the shifter, so the
    two agree in a run that flipped. The pointer alone cannot say so: photographing `A_screen_back`
    yields the PREVIOUS frame, which is a plausible picture of the wrong moment and passes every
    other check in this file. A run that never published at all fails here too — a picture of a
    buffer no flip ever put on screen is not a picture of what a player would see.
    """
    front = _u32(image, hud.A_SCREEN_FRONT)
    assert _SHOWN_BASE == front, (
        f"the run last published {_SHOWN_BASE if _SHOWN_BASE is None else hex(_SHOWN_BASE)} to the "
        f"shifter and `A_screen_front` holds {front:#x} — either nothing flipped, or this picture "
        f"would be of the buffer the flip left behind")
    return front


def _pens_of(buf):
    """Run `vbl_menu` on a COPY of the pictured state and take what it puts on the shifter.

    A copy, because the handler also ticks the raster phase and runs the sound driver: the picture's
    own world must not move because this script wanted to know its colours.
    """
    probe = harness.candidate_image(bytearray(buf))
    harness.arm_candidate()
    LIB.g_vbl_menu(probe)
    return _pens_the_run_published()


def _screen(name, image, base, pens):
    """Decode the framebuffer at `base` and hand back (name, PNG bytes).

    `st_pixels.decode_planar` is the workspace's one decoder and it REFUSES a slice that would run
    off the end of the image — a wrong base would otherwise decode as pen 0 everywhere, which is a
    blank, plausible PNG and the one failure a picture never shows.
    """
    path = OUT / f"{name}.png"
    write_png(str(path), SCREEN_WIDTH, SCREEN_HEIGHT,
              st_pixels.decode_planar(image, SCREEN_WIDTH, SCREEN_HEIGHT, offset=base), pens)
    print("  wrote", path.relative_to(WORKSPACE))
    return name, path.read_bytes()


def _publish(name, buf):
    """Photograph the buffer the run's own flip put on the shifter, in its own published palette."""
    image = bytearray(buf)
    return _screen(name, image, _the_buffer_the_shifter_is_showing(image), _pens_of(buf))


def _publish_the_back_buffer(name, buf, drawn_after, why):
    """...and the pictures whose last step draws BEHIND the shifter and never flips.

    `game_over_screen_prologue` stops at the `bsr` into the high-score arm, before the flip its
    caller would eventually make; the sprite sheets draw onto the cleared back buffer on purpose.
    Both are pictures of a buffer the player would see a moment later.

    `drawn_after` is `_publications()` taken BEFORE that last step, and requiring it not to have
    moved is what makes the docstring's claim a check: had the step flipped after all, this picture
    would be of the frame BEFORE it, and comparing the two pointers cannot notice — they are still
    distinct and the shifter still agrees with `screen_front`, which is exactly the state a
    successful flip leaves behind.
    """
    image = bytearray(buf)
    back = _u32(image, hud.A_SCREEN_BACK)
    assert _publications() == drawn_after, (
        f"{name}: the run published {_publications() - drawn_after} more screen base(s) while "
        f"drawing this picture, so it DID flip and the back buffer now holds the previous frame "
        f"({why})")
    assert _SHOWN_BASE != back, (
        f"{name}: the shifter is showing {back:#x}, which is the buffer this picture calls the back "
        f"one — the two pointers are not what this render assumes ({why})")
    return _screen(name, image, back, _pens_of(buf))


def _publications():
    """How many screen bases the run has put on the shifter so far."""
    return _PUBLISHES


# ==================================================================================================
# The boot chain, and a section over it
# ==================================================================================================
#
# Fifteen slices, in `_start`'s order, each of them one `test_init.py` verifies against the oracle.
# Four of them wait a frame on `A_vsync_flag`, a byte only the vertical-blank handler ever writes, so
# each is given the one scheduled store its own wait site needs — the same store `test_init.py`
# schedules, at the same PC.

# The wait sites, which are `test_init.py`'s (`BOOT_VSYNC_WAIT_SITE`, its raster sibling, and the two
# the attract prologue re-reads).
# Which read of the flag the release lands on. The first: each of these slices sets the flag and then
# spins, so a store before the very first read is what makes the loop run exactly once.
# `test_init._vsync_release` builds the entry itself — one spelling of the VBL handler's own store.
VSYNC_RELEASE_NTH = 1


# (glue name, the wait site it spins at or None). THE ORDER IS `zynaps_main.c`'s, which is `_start`'s:
# the prologue ends at the `bsr title_attract_loop` at 0x10520, so the attract slices run BETWEEN the
# two boot groups and not after them — `boot_stage_frontend_screens` at 0x10524 is the instruction
# that `bsr` returns to.
BOOT_PROLOGUE_SLICES = (
    ("g_boot_enter_supervisor", None),
    ("g_boot_save_vbl_vector", None),
    ("g_boot_configure_ikbd", None),
    ("g_boot_load_title_assets", None),
    ("g_boot_load_gameplay_assets", None),
    ("g_boot_install_ikbd_isr", None),
    ("g_boot_front_end_prologue", None),
)

# `title_attract_loop`'s four slices, less the fourth: `attract_wait_for_start` is the loop that
# waits for a key or the fire button, and a picture wants the page it drew rather than the wait
# after it. What that costs is one byte — the slice writes `player_count` on every pass, and this
# run therefore starts the two-player game the shipped image's zero already asks for.
ATTRACT_SLICES = (
    ("g_attract_program_timer_b", boot.ATTRACT_VSYNC_WAIT_SITE_SETUP),
    ("g_attract_program_rasterbar_timer", boot.ATTRACT_VSYNC_WAIT_SITE_ARMED),
    ("g_attract_build_colour_bars", None),
)

# ...and what the `bsr` returns to, down to the section chain.
BOOT_AFTER_ATTRACT_SLICES = (
    ("g_boot_stage_frontend_screens", None),
    ("g_boot_program_timer_b", boot.BOOT_VSYNC_WAIT_SITE),
    ("g_boot_program_raster_timer", boot.BOOT_VSYNC_WAIT_SITE_RASTER),
    ("g_boot_enable_interrupts", None),
    ("g_boot_new_game_records", None),
)



def _run_slice(buf, name, site=None, schedule=None):
    """One slice, armed the way `harness.differential` arms a candidate before every case.

    `site` is the shorthand every boot slice needs — one vertical-blank release at one wait site.
    `schedule` is the long form, for the one slice whose wait is a different store at a different
    site. Both go through here rather than round it, so the arm, the shifter note and the
    refused-OS-call check happen once and cannot drift apart.

    Returns whatever the glue answered — several of these slices report which arm they took, and
    the callers below assert on those answers rather than letting them fall on the floor.
    """
    assert site is None or schedule is None, f"{name}: give a wait site or a schedule, not both"
    if site is not None:
        schedule, sites = boot._vsync_release(site, VSYNC_RELEASE_NTH), [site]
    else:
        schedule, sites = schedule or [], [entry["pc"] for entry in schedule or []]
    harness.arm_candidate(scheduled=emu.schedule_entries(schedule), sites=sites)
    answer = getattr(LIB, name)(buf)
    _note_the_publish()
    assert LIB.g_os_refusal_count() == 0, (
        f"{name} made an OS call the kit's TOS model refused ({harness.refusal_hints()}) — the "
        f"picture that follows would be of a run that did not happen")
    return answer


def _staged_image(files, substitutions=None):
    """A fresh image with the named disk files staged, `substitutions` swapping what a name serves.

    `harness.stage_files` is what refuses more files than the model has slots, and its message says
    what a thirty-third would overwrite — so there is no count check here to shadow it with a worse
    one.
    """
    swap = substitutions or {}
    pokes, _handles = harness.stage_files(
        [(name, (DISK / swap.get(name, name).upper()).read_bytes()) for name in files])
    _begin_a_run()
    return harness.candidate_image(harness.make_image(pokes))


def _boot_to_the_attract_loop(files, substitutions=None):
    """`_start` from its first instruction to the `bsr` at 0x10520, and the attract page it draws."""
    buf = _staged_image(files, substitutions)
    for name, site in BOOT_PROLOGUE_SLICES + ATTRACT_SLICES:
        _run_slice(buf, name, site)
    return buf


def _stage_section(section, substitutions=None):
    """...and on through the rest of `_start` into one level section, to the frame loop's own head.

    THE WHOLE CHAIN, in `recreate/atari/zynaps_main.c`'s order, which is the original's: advance,
    ask whether a reload is needed, redraw the two intro screens, load the section's assets, reset
    for the life, pre-fill the scroll pages. The explicit `section_reload_intro_screens` call is
    there because `play_one_game` makes it explicitly, NOT because these pictures need it —
    `section_restart_prologue` below makes the same call itself (`recreate/src/init.c`), and dropping
    the explicit one leaves every PNG byte-identical. Measured, rather than assumed either way.

    THE ONE STAGED BYTE is the section the game is about to advance INTO. `boot_new_game_records`
    leaves `level_section` at 0xff for `section_advance` to bump to 0, so the opener needs no poke at
    all; a later section is reached by putting the counter one short of it and letting the game's own
    `addi.b` do the arithmetic, rather than by writing the answer.
    """
    files = list(boot.BOOT_FILES) + list(boot.GAMEPLAY_FILES) + list(boot._section_files(section))
    buf = _boot_to_the_attract_loop(files, substitutions)
    for name, site in BOOT_AFTER_ATTRACT_SLICES:
        _run_slice(buf, name, site)

    buf[boot.A_LEVEL_SECTION] = (section - 1) & 0xff
    _run_slice(buf, "g_section_advance")
    assert buf[boot.A_LEVEL_SECTION] == section, (
        f"`section_advance` left the counter at {buf[boot.A_LEVEL_SECTION]}, not the section "
        f"{section} this picture is of")
    assert _run_slice(buf, "g_section_reload_needed"), (
        f"the flow says section {section}'s assets are already loaded, so the load below would not "
        f"run in the game and this staging is not the game's")
    _run_slice(buf, "g_section_reload_intro_screens")
    took_the_map_arm = _run_slice(buf, "g_section_load_assets")
    assert bool(took_the_map_arm) == (section not in boot.ASTEROID_SECTIONS), (
        f"section {section} took the {'map' if took_the_map_arm else 'asteroid'} arm of "
        f"`section_load_assets`, which is not the arm its type byte names")
    _run_slice(buf, "g_section_restart_prologue")
    _run_slice(buf, "g_section_start_prefill")
    assert buf[boot.A_LEVEL_SECTION_LOADED] == section, (
        f"the flow believes it has section {buf[boot.A_LEVEL_SECTION_LOADED]}'s assets loaded, not "
        f"section {section}'s")
    return buf


def _cross_the_fire_gate(buf):
    """`section_start_tail`: PREPARE FOR COMBAT, until the player presses fire.

    The one slice whose wait is not the vertical blank: it sends an IKBD interrogate and polls the
    byte the reply lands in, so the scheduled store is the joystick's, on the read `test_frame` says.
    """
    _run_slice(buf, "g_section_start_tail", schedule=[
        {"pc": frame.SECTION_TAIL_FIRE_WAIT_PC, "nth": frame.SECTION_TAIL_FIRE_NTH,
         "addr": frame.A_JOYSTICK_STATE, "width": 1, "value": frame.JOYSTICK_FIRE}])


def _step(buf, joystick):
    """One whole frame of the game, and which of `frame_loop_once`'s five exits it left through."""
    buf[frame.A_JOYSTICK_STATE] = joystick
    harness.arm_candidate(scheduled=emu.schedule_entries(list(frame.FRAME_SCHED)),
                          sites=list(frame.WAIT_SITES))
    exit_code = LIB.g_frame_loop_once(buf, CARRIED_CHANCE_INDEX, CARRIED_GROUND_SPAWN_Y)
    _note_the_publish()
    return exit_code


# `frame_loop_once`'s two carried registers, as `recreate/atari/zynaps_main.c` passes them on the
# machine: there is no oracle on target to read them from either, and the frame differential against
# the shipped binary is run with exactly these.
CARRIED_CHANCE_INDEX = 0
CARRIED_GROUND_SPAWN_Y = 0


def _live_entities(image):
    """Live records of the entity table — `recreate/atari/bench_tier.live_slots`' own test, counted."""
    return sum(1 for slot in range(frame.ENTITY_SLOTS)
               if image[frame.entity_record(slot) + frame.ENTITY_ALIVE])


def _live_asteroids(image):
    """...and of the asteroid array, which an asteroid section flies instead of the entity table."""
    return sum(1 for record in range(boot.SECTION_RESTART_ASTEROID_RECORDS)
               if image[boot.A_ASTEROID_RECORDS + record * frame.ENTITY_STRIDE
                        + frame.ENTITY_ALIVE])


def _lap(buf, number, what):
    """One frame of the fixed script, refusing a run that ends before the picture it is of.

    If the ship is lost or the section ends first, the caption this frame is about would be
    describing something else, so the run stops with a sentence rather than publishing what it
    happened to land on.
    """
    exit_code = _step(buf, _STREAM.choice(frame.JOYSTICK_BYTES))
    assert exit_code == FRAME_EXIT_NEXT_FRAME, (
        f"{what}: the frame loop left through exit {exit_code} at frame {number}, before the "
        f"picture this run is of")


def _play_exactly(frames):
    """Stop after a STATED number of frames, for a picture that is of a moment rather than a state."""
    def stop_after(buf, what):
        for number in range(1, frames + 1):
            _lap(buf, number, what)
        return frames, "stopped at the frame this picture is named for"
    return stop_after


def _play_until(census, wanted, subject):
    """Stop at the FIRST frame whose census reaches `wanted` — searched for, never typed.

    `wanted` must beat what the section start already has, or "busy" would be a claim about nothing:
    a census of zero would keep frame 1, which is the ship, its shadow and the drone on an empty
    playfield. The floor is the staged world's own count, so it is measured rather than asserted.
    """
    def stop_when_busy(buf, what):
        floor = census(bytearray(buf))
        assert wanted > floor, (
            f"{what}: the census wants {wanted} {subject} and the section start already has "
            f"{floor}, so the first frame would meet it and the picture would be of the start")
        for number in range(1, PLAY_FRAMES + 1):
            _lap(buf, number, what)
            if census(bytearray(buf)) >= wanted:
                return number, f"{wanted}+ {subject}"
        raise AssertionError(f"{what}: no frame in {PLAY_FRAMES} reached {wanted} {subject}")
    return stop_when_busy


# ==================================================================================================
# The front end — the two pages the attract loop alternates
# ==================================================================================================

def render_front_end():
    """The title page and the role of honour, drawn by the loop that alternates them.

    `attract_build_colour_bars` builds the raster list, uploads the front-end palette — the upload
    this picture's pens come from — and calls `title_screen_draw`, which lays the three strips of
    ZYNLOGO.DAT and then runs straight on into HEWLOGO.DAT, whose bytes `_start` loaded at the very
    next address. `attract_next_page` then swaps to `role_of_honour_screen` on its own timer, and
    that is the second call here: the same three logo strips, the heading, and the five rows of the
    high-score table — which are the SHIPPED image's own, not a game's: `boot_new_game_records`
    rewrites the player records and leaves that table alone (measured — dropping the slice moves no
    pixel of this picture).

    Both pages draw into the back buffer and end in `screen_flip_buffers`, so the page each one just
    finished is the one on the shifter, and `_publish` is what checks that rather than assuming it.
    The palette is the one thing here that is NOT read through the vertical-blank handler: at this
    point in the boot no handler has uploaded anything, so the pens are taken from
    `attract_build_colour_bars`' own upload, in the run that drew the page.
    """
    buf = _boot_to_the_attract_loop(list(boot.BOOT_FILES) + list(boot.GAMEPLAY_FILES))
    image = bytearray(buf)
    base = _the_buffer_the_shifter_is_showing(image)
    pens = _pens_the_run_published()      # `attract_build_colour_bars`' own upload, in this run
    pictures = [_screen("title", image, base, pens)]

    _run_slice(buf, "g_role_of_honour_screen", None)
    image = bytearray(buf)
    honour = _screen("role-of-honour", image, _the_buffer_the_shifter_is_showing(image), pens)
    assert honour[1] != pictures[0][1], (
        "the role of honour is the same picture as the title page, so the page swap drew nothing")
    return pictures + [honour]


# ==================================================================================================
# A section: the gate, the opening, and a frame with the table full
# ==================================================================================================

def render_section_start():
    """PREPARE FOR COMBAT — the screen the section start holds until the player presses fire.

    Everything in it is the boot chain's: `status_panel_build_master` composed the panel out of
    STATUS.PI1's three strips, `section_restart_prologue` stamped it into both buffers and called
    `player_intro_screen`, which draws the ZYNAPS logo, the player's digit and the two messages.
    """
    buf = _stage_section(SECTION_OPENER)
    return [_publish("prepare-for-combat", buf)]


def _play_picture(name, section, how):
    """One play picture: stage the section, cross the fire gate, and let `how(buf, name)` stop."""
    buf = _stage_section(section)
    _cross_the_fire_gate(buf)
    number, what = how(buf, name)
    print(f"  {name}: section {section + 1}, {what} at frame {number}, "
          f"{_live_entities(bytearray(buf))} live entities, "
          f"{_live_asteroids(bytearray(buf))} asteroid records")
    return _publish(name, buf)


def render_play():
    """Five frames of the game playing itself, over four of its sixteen sections.

    The opening one is a stated frame number because "the start" is what it is a picture of; the
    other four stop at the first frame that meets a census, so no caption below can outlive the run
    that earned it.
    """
    busy = _play_until(_live_entities, BUSY_ENTITIES, "live entity records")
    return [_play_picture(name, section, how) for name, section, how in (
        ("section1-start", SECTION_OPENER, _play_exactly(OPENING_FRAME)),
        ("section1-busy", SECTION_OPENER, busy),
        ("section2-asteroids", SECTION_ASTEROIDS,
         _play_until(_live_asteroids, BUSY_ROCKS, "asteroids in flight")),
        ("section9-busy", SECTION_MAGENTA, busy),
        ("section12-busy", SECTION_CAVERN, busy))]


def render_game_over():
    """`game_over_screen_prologue` — the back buffer cleared and GAME OVER PLAYER 1 drawn over it.

    The prologue and not the whole screen: `game_over_screen` runs straight on into
    `highscore_check_and_insert`, whose rated arm is a keyboard loop typing a name one console key
    per call, and this set has no keyboard in it. The prologue is the slice that ends at the `bsr`
    into that arm, and it is one `test_highscore.py` verifies whole.

    The fire gate is crossed first so the pens are the ones a player would be looking at: the
    section start is what commits `palette_next` into the row the vertical blank uploads, and a game
    over reached without that would be drawn in the front end's colours instead of the section's.
    """
    buf = _stage_section(SECTION_OPENER)
    _cross_the_fire_gate(buf)
    before = _publications()
    _run_slice(buf, "g_game_over_screen_prologue")
    return [_publish_the_back_buffer("game-over", buf, before,
                                     "the prologue stops before its caller's flip")]


# ==================================================================================================
# The archaeology plate — a file on the disk that no load site opens
# ==================================================================================================
#
# ROTBALLS.DAT is one of three game files the binary's filename table cannot name (`README.md`,
# "Files on the disk that no load site opens"): 360 bytes, four frames of a rotating pair of chrome
# spheres, in exactly the masked 16x9 geometry and byte count of the MISSILE1-3.DAT the game does
# load. The two sheets below are how that claim is shown rather than asserted — the cut file is
# served to the section flow WHERE ITS OWN MISSILE FILE WOULD GO, and the flow loads it, splits it
# and preshifts it without noticing, because it is a drop-in fourth sprite set.
#
# What the sheet chooses is what a sheet must: where the frames are put. Everything else is the
# game's — the bytes are the file's, the four bank addresses are checked against the file's own
# frames before anything is drawn, and the blit is `draw_sprite_masked` at an x on a cell boundary,
# which is the arm that reads a bank slot unshifted.

SPRITE_SHEET_FRAMES = 4              # what the section flow splits a missile file into
SHEET_FIRST_X = 64                   # the leftmost frame's cell...
SHEET_X_STEP = 48                    # ...and the gap to the next, both multiples of the cell width
SHEET_Y = 80                         # inside the playfield, clear of the panel
# `draw_sprite_masked`'s third argument is the bank's HALF-FRAME STRIDE, which it multiplies by the
# sub-cell phase `x & 0xf` to pick a preshift slot (recreate/src/sprite.c). Every x below is cell-aligned, so
# that phase is 0 and the product is 0 whatever the stride — which is what lets a sheet of unshifted
# frames name a stride it does not have. The alignment is asserted rather than left to the constants.
SPRITE_UNSHIFTED_STRIDE = 0

# The four banks the section flow leaves a missile file's frames in:
# `recreate/src/init.c`'s
# SECTION_MISSILE_SRC and SECTION_MISSILE_FRAME_1..3. They are restated here rather than borrowed —
# `test_enemy.A_WAVE_TRIO_SPRITE` is the same number under a different meaning, and borrowing it
# would couple this sheet to a constant that is free to move on its own. What pins them is stronger
# than an address mirror: `_assert_the_banks_are_the_file` compares every drawn bank against the
# FILE's own frame, so a wrong address fails naming the frame it failed on.
MISSILE_FRAME_BANKS = (0x60bbe, 0x60c18, 0x60e8e, 0x60ee8)


def _assert_the_banks_are_the_file(image, blob, what):
    """Every bank drawn holds its own frame of the file, byte for byte; answer the frame's rows."""
    assert len(blob) == SPRITE_SHEET_FRAMES * (len(blob) // SPRITE_SHEET_FRAMES), (
        f"{what}: {len(blob)} bytes does not divide into {SPRITE_SHEET_FRAMES} equal frames, so "
        f"the trailing bytes would be dropped and the sheet would not be the whole file")
    frame_bytes = len(blob) // SPRITE_SHEET_FRAMES
    assert frame_bytes % sprite.SPRITE_MASKED_ROW_BYTES == 0, (
        f"{what}: a frame of {frame_bytes} bytes is not whole rows of "
        f"{sprite.SPRITE_MASKED_ROW_BYTES}")
    for index, bank in enumerate(MISSILE_FRAME_BANKS):
        want = blob[index * frame_bytes:(index + 1) * frame_bytes]
        assert bytes(image[bank:bank + frame_bytes]) == want, (
            f"{what}: the bank at {bank:#x} is not frame {index} of the file, so this sheet would "
            f"be a picture of something else")
    return frame_bytes // sprite.SPRITE_MASKED_ROW_BYTES


def _sprite_sheet(name, source_file, what):
    """One row of the four frames the section flow made out of `source_file`."""
    section_file = next(f for f in boot._section_files(SECTION_OPENER) if f.startswith("missile"))
    buf = _stage_section(SECTION_OPENER, substitutions={section_file: source_file})
    blob = (DISK / source_file.upper()).read_bytes()
    rows = _assert_the_banks_are_the_file(bytearray(buf), blob, what)

    before = _publications()
    LIB.g_playfield_clear(buf)
    record = boot.A_ENTITY_GUNSIGHT      # a record the game owns, borrowed as the sheet's easel
    for index, bank in enumerate(MISSILE_FRAME_BANKS):
        x = SHEET_FIRST_X + index * SHEET_X_STEP
        assert x % st_pixels.PIXELS_PER_WORD == 0, (
            f"{what}: frame {index} would be drawn at x={x}, which is not on a cell boundary — the "
            f"blit would take a sub-cell phase and index the bank by a stride this sheet passes as "
            f"zero, drawing unshifted art at a shifted x")
        buf[record + frame.ENTITY_X:record + frame.ENTITY_X + 2] = x.to_bytes(2, "big")
        buf[record + frame.ENTITY_Y:record + frame.ENTITY_Y + 2] = SHEET_Y.to_bytes(2, "big")
        buf[record + frame.ENTITY_HEIGHT:record + frame.ENTITY_HEIGHT + 2] = rows.to_bytes(2, "big")
        buf[record + frame.ENTITY_SPRITE:record + frame.ENTITY_SPRITE + 4] = bank.to_bytes(4, "big")
        LIB.g_draw_sprite_masked(buf, record, SPRITE_UNSHIFTED_STRIDE)
    print(f"  {name}: {source_file}, {rows} rows a frame")
    return _publish_the_back_buffer(name, buf, before,
                                    "a sheet is drawn on the cleared back buffer")


def render_cut_sprites():
    """The cut file beside the one it is shaped like, drawn by the same blitter in the same places.

    Both sheets are the same run with one thing different: which bytes the staged-file model hands
    back when `section_load_assets` asks for the section's missile file. The two pictures differ, and
    the assertion below is what says the difference is the file and not the run.
    """
    shipped = _sprite_sheet("missile-frames", "missile1.dat", "the shipped missile frames")
    cut = _sprite_sheet("cut-rotballs", "rotballs.dat", "the cut ROTBALLS frames")
    assert shipped[1] != cut[1], (
        "the two sprite sheets are the same picture, so serving ROTBALLS.DAT in the missile file's "
        "place changed nothing — this plate would be showing the shipped art twice")
    return [shipped, cut]


# ==================================================================================================

def render_everything():
    """Every picture, in README order; returns [(name, PNG bytes)]."""
    pictures = render_front_end()
    pictures += render_section_start()
    pictures += render_play()
    pictures += render_game_over()
    pictures += render_cut_sprites()
    return pictures


def main():
    """Render the set twice and require the two to agree, then say what was written.

    THE SECOND RENDERING IS THE POINT: "byte-identical every run" is the property that lets these
    PNGs be tracked in git, and the run is quick enough to assert it rather than assume it.

    BOTH PASSES WRITE, so what is on disk after a mismatch is the SECOND run's picture and not the
    first — the two digests in the message are the record of what differed. The thing being claimed
    is about the FILES, so rendering the second pass somewhere else would prove it of something else.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    first = render_everything()
    print("...and again, to prove the set is a function of the binary and its own data files")
    second = render_everything()
    assert [name for name, _ in first] == [name for name, _ in second], (
        "the two runs rendered different pictures, so the SET itself is not reproducible")
    for (name, before), (_, after) in zip(first, second):
        assert before == after, (
            f"{name}.png differs between two runs of this script — something in the set is not a "
            f"function of the binary and the game's own files (sha256 "
            f"{hashlib.sha256(before).hexdigest()} vs {hashlib.sha256(after).hexdigest()})")
    print(f"  {len(first)} pictures, byte-identical over two runs")


if __name__ == "__main__":
    main()
