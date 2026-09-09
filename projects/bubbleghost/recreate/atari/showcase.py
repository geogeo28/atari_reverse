#!/usr/bin/env python3
"""showcase.py — the README gallery: nine pictures, every one DRAWN BY BUBBLE.PRG on a 68000.

    bash atari/build.sh play && python3 atari/showcase.py

WHAT A PICTURE HERE IS. Four Hatari runs of the `play` build — the same binary and the same machine
`smoke.py` judges, booted the same way — each driven to a moment by the game's OWN keys, and at that
moment the DISPLAYED framebuffer is `savebin`ned out of the emulator and decoded into a 320x200 PNG
by `../../../../tools/st_pixels.py`, the workspace's one plane model. Nothing here is screenshotted
and nothing here comes from the original binary or from a data file: these are the reconstruction's
own 32,000 bytes, the ones `smoke.py` compares against the shipped program's.

WHY THE FRAMEBUFFER AND NOT A SCREENSHOT. Hatari's `screenshot` grabs the last RENDERED surface,
which is built scanline by scanline, so a capture taken where a breakpoint fires mixes that frame
with the one before it and has to be SETTLED first (`smoke.py`, `arm_the_anchor`). A settle is a
wall of vertical blanks the program keeps running through — which a static screen can afford and a
moving one cannot: the attract mode's replay has no `Vsync` in it at all (`../notes/frontend.md`
§2), so how far it gets in three blanks depends on where in the raster the key landed. Memory is
exact AT THE INSTRUCTION, so a `savebin` at the breakpoint is the moment the breakpoint names, on
every one of these screens, moving or not.

THE PALETTE IS THE ONE THING READ LATE — three vertical blanks after the instruction. XBIOS
`Setpalette` is DEFERRED: TOS loads the sixteen colour registers from its own vertical-blank
handler, so the chip AT a breakpoint can still be showing the palette of the frame before, which is
what the XBIOS door was built for and what `smoke.py`'s voice anchor asserts. Nothing in any of
these windows uploads a second palette between the instruction and the read, so three blanks later
IS this picture's palette.

HOW EACH MOMENT IS CHOSEN — a symbol and an ARRIVAL COUNT, never a wall clock. Every shot below
names a function of the reconstruction (`m68k-elf-nm` over the linked ELF, placed at the base the
shim's own anchor table publishes) and which arrival at it to photograph, so the moment is a place
in the program rather than a delay. The keys are sent by `smoke.press_the_menu_keys`, which resends
until the game's own screen changes, for the reason its docstring gives.

WHAT IS ASSERTED, per picture and across the set:

  * every picture holds more than one colour — a one-colour capture is a photograph of nothing, and
    is the failure that looks most like a success (`smoke.CHECK_NOT_BLANK`)
  * the two demo frames put the GHOST in different places, so the later one is a later moment and
    not the same record photographed twice
  * the two slideshow pictures published are different ROOMS, read off `A_room_number` at the same
    instruction as the picture — three are photographed and the first two that differ are published
  * the hall of fame was photographed with the hall's own backdrop room on the screen, which is what
    tells it from the other two callers of the animation step it breaks on
  * the two room-1 frames are different pictures, and the room is still live at the second. It is
    the pictures that are compared and not the bubble, because THE BUBBLE DOES NOT MOVE ON ITS OWN:
    nothing blows it while the mouse is still, and what turns between the two frames is the fans,
    the ghost's own animation and the bonus bar
  * ACROSS INVOCATIONS: every deterministic picture's sha256 is stored in `out/showcase/hashes.txt`
    and re-checked on the next run, which refuses when one moves. The manifest is written only once
    everything has passed, so a failing run leaves the baseline it failed against intact. The run is
    not doubled inside this script the way Zynaps' renderer doubles its own — a picture here costs a
    whole Hatari boot, so the pair check is two invocations
  * the machine itself: each scene's exit status and its own log, through
    `smoke.check_machine_health`, because every marker can land on a build that faults a moment
    later and the pictures would look perfectly plausible

WHAT IS NOT DETERMINISTIC, AND WHY IT CANNOT BE. The slideshow picks each room with XBIOS `Random`,
which is seeded off the machine's own clock, so which rooms it shows depends on when the `D` key
landed. Those two pictures are therefore re-drawn by every invocation and are not in the manifest at
all; the README's caption names the rooms THIS run drew rather than promising a room. Everything
else — the presentation, the menu, the demo replay, the first room, the hall of fame — is a function
of the arrival count alone and is byte-identical run to run.
"""
import hashlib
import shutil
import struct
import sys
import time
from collections import namedtuple
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# ...AND tools/ IN ITS OWN RIGHT, for `profile.py`'s reason: `smoke` puts it on the path as a side
# effect of being imported, and an import sorter that moved the line below above `import smoke`
# would kill this module at import before any of its own diagnostics could fire.
REPO = HERE.parents[3]                 # atari -> recreate -> bubbleghost -> projects -> the repo
sys.path.insert(0, str(REPO / "tools"))
import mkprg                                                                      # noqa: E402
import smoke                                                                      # noqa: E402
import st_pixels                                                                  # noqa: E402
from extract_graphics import write_png                                            # noqa: E402
from hatari_headless import (                                                     # noqa: E402
    HeadlessSession, action_file, await_file, distinct_colours, same_picture, settle_chain,
)

ELF = smoke.HERE / "build" / "bubble.elf"
WORK = smoke.OUT / "showcase"
ASSETS = REPO / "assets" / "bubbleghost"
MANIFEST = WORK / "hashes.txt"
# The symbol whose RUNTIME address the shim's anchor table publishes, and so the one that places
# every other — `profile.py`'s `FRAME_SYMBOL`, for the same reason and by the same arithmetic.
FRAME_SYMBOL = "game_frame_update"

# ---- the picture ---------------------------------------------------------------------------------
# Derived, not typed: the row stride is the blit subsystem's own and the plane model is the
# workspace's, so a screen that changed shape would move both of these rather than disagree with them.
SCREEN_ROW_BYTES = smoke.scrape_define(smoke.BLIT_H, "SCREEN_ROW_BYTES")
SCREEN_WIDTH = SCREEN_ROW_BYTES // st_pixels.group_bytes() * st_pixels.PIXELS_PER_WORD
SCREEN_ROWS = smoke.SCREEN_BYTES // SCREEN_ROW_BYTES
# ...and how many, from the file that MEASURED it rather than as a second number for one fact:
# `smoke.arm_the_voice_anchor` reads the presentation's palette this many blanks after the
# same class of instruction, and asserts it against GHOST.PRE's own sixteen words.
PALETTE_SETTLE_VBLS = smoke.VOICE_SETTLE_VBLS

# ---- the globals a shot reads at its own instruction ----------------------------------------------
GAMEPLAY_H = smoke.RECREATE / "include" / "gameplay.h"
A_room_number = smoke.scrape_define(GAMEPLAY_H, "A_room_number")
A_in_room = smoke.scrape_define(GAMEPLAY_H, "A_in_room")
A_ghost_y = smoke.scrape_define(GAMEPLAY_H, "A_ghost_y")     # x is the word above y, so one probe
A_bubble_y = smoke.scrape_define(GAMEPLAY_H, "A_bubble_y")   # reads the pair (../notes/frontend.md)
HALL_BACKDROP_ROOM = smoke.scrape_define(smoke.RECREATE / "include" / "frontend.h",
                                         "HALL_BACKDROP_ROOM")
WORD_BYTES = 2
SPRITE_POSITION_BYTES = 2 * WORD_BYTES

# ---- the menu's own keys, as ST scancodes ----------------------------------------------------------
# `menu_read_key_and_fold` folds to upper case, so these are the letters a player presses.
KEY_D = 0x20                     # the attract mode: the GHOST.DEM replay, then the room slideshow
KEY_H = 0x23                     # the hall of fame

# ONE BUDGET FOR A WHOLE SCENE — its keys and its shots together, because they are one timeline and
# two budgets would bound neither. It cannot usefully exceed the machine's own life: every run is
# capped at `smoke.RUN_VBLS` vertical blanks (~240 emulated seconds), and emulation here is about
# real time, so a Hatari that outlived this deadline would already have exited on its own. The
# attract scene is the one that needs the room: its replay feeds 980 records with no `Vsync` in the
# loop, so DEMO_LATE_RECORD alone is ~40 emulated seconds.
SCENE_DEADLINE_SECONDS = 300

# WHICH ARRIVALS THE PICTURES ARE TAKEN AT. Each is a place in the program; the reasons are in the
# `Shot.why` lines below, which is also what the README's captions are written from.
ROOM_FIRST_DRAWN_FRAME = 2       # `smoke.arm_the_room_anchor`: at arrival 1 nothing is drawn yet
ROOM_LATER_FRAME = 90            # ~5 emulated seconds on, and well short of any death sequence
DEMO_EARLY_RECORD = 400
DEMO_LATE_RECORD = 720           # of the 980 the replay feeds; both are past the palette upload
# THE SLIDESHOW IS PHOTOGRAPHED ONE ARRIVAL LATE, and that is not an off-by-one. Each arrival at
# `menu_attract_slideshow_room` DRAWS a room and holds it, so at the arrival's own entry the screen
# still carries the previous hold — which is that room's last presented frame, and which is why
# `A_room_number`, read at the same instruction, is the room in the picture rather than the one
# about to be drawn. Arrival 1 would therefore photograph the demo's last frame.
SLIDESHOW_ARRIVALS = (2, 3, 4)

Probe = namedtuple("Probe", "label offset size")
GHOST_POSITION = Probe("ghost y,x", A_ghost_y, SPRITE_POSITION_BYTES)
BUBBLE_POSITION = Probe("bubble y,x", A_bubble_y, SPRITE_POSITION_BYTES)
ROOM_NUMBER = Probe("room", A_room_number, WORD_BYTES)
IN_ROOM = Probe("in room", A_in_room, WORD_BYTES)

# A picture: the file it lands in, the function and arrival that choose its moment, the globals read
# at that same instruction (every one of them REPORTED; the checks below assert on some of them),
# and what it is a picture OF. Whether two runs must agree on it is `is_deterministic`, derived.
Shot = namedtuple("Shot", "name symbol arrival probes why")

PRESENTATION = Shot(
    "title", "enter_the_voice_player", 1, (),
    "GHOST.PRE as the reconstruction drew it, at the instruction that hands control to GHOST.LOA "
    "and starts the speech — so the palette is the presentation's own, through the XBIOS door")
MENU = Shot(
    "menu", "menu_read_key_and_fold", 1, (),
    "the four Press [G]/[P]/[D]/[H] lines, at the read that blocks on them — the same place "
    "smoke.py photographs the original")
DEMO_EARLY = Shot(
    "demo-early", "demo_play_record", DEMO_EARLY_RECORD, (GHOST_POSITION,),
    f"GHOST.DEM record {DEMO_EARLY_RECORD} of 980, replayed into room 1 by the attract mode's [D]")
DEMO_LATE = Shot(
    "demo-late", "demo_play_record", DEMO_LATE_RECORD, (GHOST_POSITION,),
    f"...and record {DEMO_LATE_RECORD}, with the ghost somewhere else in the same room")
# THE CANDIDATES ARE NUMBERED AND THE PUBLISHED SLOTS ARE LETTERED, because they are not the same
# thing: three rooms are photographed and the first two that came out DIFFERENT fill the gallery's
# two slots, which are the names the READMEs point at.
SLIDESHOW = tuple(
    Shot(f"slideshow-{candidate}", "menu_attract_slideshow_room", arrival, (ROOM_NUMBER,),
         "a random room of the attract mode's slideshow, at the instruction that ends its hold")
    for candidate, arrival in enumerate(SLIDESHOW_ARRIVALS, start=1))
SLIDESHOW_SLOTS = ("slideshow-a", "slideshow-b")
ROOM_START = Shot(
    "room1-start", FRAME_SYMBOL, ROOM_FIRST_DRAWN_FRAME, (BUBBLE_POSITION,),
    "room 1 after [G] and [1], one whole frame in — the first moment the ghost and the bubble have "
    "been through the GEM door onto the visible screen")
ROOM_BUSY = Shot(
    "room1-busy", FRAME_SYMBOL, ROOM_LATER_FRAME, (BUBBLE_POSITION, IN_ROOM),
    f"...and {ROOM_LATER_FRAME} frames in, with the fans turned and the bonus bar down")
# `objects_animate_and_draw` IS ALSO THE DEMO'S AND THE SLIDESHOW'S animation step, and in this
# scene neither runs: the menu blocks on `Cnecin` until a key arrives and the only key sent is `H`.
# The room probe is that assumption's surface — `menu_hall_of_fame` puts `A_room_number` back to the
# backdrop room before its idle loop, so a picture taken anywhere else reads a different room.
HALL = Shot(
    "hall-of-fame", "objects_animate_and_draw", 1, (ROOM_NUMBER,),
    "the hall of fame: the five SCORE rows over room 0, at the idle loop's first animation step — "
    "which is the first instruction after the table, the backdrop and the HUD row are all on screen")

# A scene: one Hatari boot, ONE key path, and every shot that path reaches. Four boots rather than
# one because the attract mode's last phase is 37,000 mouse polls with nothing in them, so a run
# that waited for [D] to hand the menu back would spend its whole budget there. `front` keeps its
# own boot for a cheaper reason: the two pictures before any key are reachable from every scene, and
# giving them to one of the keyed ones would lose them whenever that key path failed.
Scene = namedtuple("Scene", "name keys entry_symbol shots")
SCENES = (
    Scene("front", (), None, (PRESENTATION, MENU)),
    Scene("attract", (KEY_D,), "menu_attract_sequence", (DEMO_EARLY, DEMO_LATE) + SLIDESHOW),
    Scene("room", (smoke.KEY_G, smoke.KEY_ONE), FRAME_SYMBOL, (ROOM_START, ROOM_BUSY)),
    Scene("hall", (KEY_H,), "menu_hall_of_fame", (HALL,)),
)


def elf_offsets():
    """`nm` over the linked ELF as {name: link-time offset}, for the symbols the shots name.

    `tos.ld` links at base 0, so these are offsets into the flat image; the base TOS chose is added
    by `text_base`. Only the shots' own symbols are kept, and a missing one is fatal here rather
    than at the breakpoint — Hatari would accept an address of 0 and simply never fire.
    """
    wanted = {shot.symbol for scene in SCENES for shot in scene.shots}
    wanted |= {scene.entry_symbol for scene in SCENES if scene.entry_symbol}
    wanted.add(FRAME_SYMBOL)
    placements = {}
    for address, _, name in mkprg.nm_rows(ELF):
        if name in wanted:
            placements.setdefault(name, set()).add(address)
    # ...and a name at two addresses is refused rather than resolved: a dict comprehension would keep
    # whichever row `nm` printed last, arm the breakpoint on the other one, and report the picture as
    # a moment the run never reached (`profile.py`'s `symbol_map` refuses the same case).
    doubled = sorted(name for name, addresses in placements.items() if len(addresses) > 1)
    if doubled:
        raise SystemExit(f"ERROR: {ELF} places {', '.join(doubled)} at more than one address, so "
                         f"there is no one instruction to photograph at")
    offsets = {name: addresses.pop() for name, addresses in placements.items()}
    missing = sorted(wanted - set(offsets))
    if missing:
        raise SystemExit(f"ERROR: {ELF} carries no {', '.join(missing)} — this file names the "
                         f"reconstruction's own functions, and one that has been renamed or inlined "
                         f"away has no address to photograph at")
    return offsets


def text_base(anchors, offsets):
    """Where TOS put our text: the anchor table's runtime PC for the frame symbol, less its offset.

    A WRONG BASE DOES NOT COME BACK EMPTY — a breakpoint on the wrong address simply never fires,
    which reads exactly like a moment the run never reached. So a base the arithmetic cannot support
    is refused here; `profile.py` pins its own against the machine's `e TEXT`, which nothing outside
    an action file can ask for.
    """
    base = anchors[smoke.ANCHOR_ROOM_FRAME] - offsets[FRAME_SYMBOL]
    if base <= 0:
        raise SystemExit(f"ERROR: the shim published {anchors[smoke.ANCHOR_ROOM_FRAME]:#x} for "
                         f"{FRAME_SYMBOL}, which is below its own link-time offset "
                         f"{offsets[FRAME_SYMBOL]:#x} — the .PRG and {ELF} are not the same "
                         f"build. Run `bash atari/build.sh play` and try again")
    return base


def shot_files(shot):
    """Where one shot's dumps land. Named per shot: two shots sharing a file would read each other's."""
    return {"screen": WORK / f"{shot.name}_screen.bin", "pens": WORK / f"{shot.name}_pens.bin",
            "done": WORK / f"{shot.name}_done.bin",
            **{probe.label: WORK / f"{shot.name}_{probe.offset:x}.bin" for probe in shot.probes}}


def arm_the_shot(session, shot, pc, image_base):
    """Break at the shot's arrival, dump the screen and its probes THERE, and the pens three blanks on.

    The two halves are deliberately not taken together — see this file's header: the framebuffer is
    exact at the instruction and the colour registers are not, because `Setpalette` is deferred. The
    last thing written is a one-byte marker, so the driver waits on the capture rather than on a
    guess.
    """
    files = shot_files(shot)
    for stale in files.values():
        stale.unlink(missing_ok=True)
    pens = action_file(
        WORK, f"{shot.name}_pens.txt",
        f"savebin {files['pens']} ${smoke.HW_PALETTE_BASE:x} "
        f"${smoke.PALETTE_PENS * smoke.PEN_BYTES:x}",
        f"savebin {files['done']} ${smoke.HW_SHIFTER_MODE:x} $1")
    settle = settle_chain(WORK, PALETTE_SETTLE_VBLS - 1, pens, f"{shot.name}_wait%d.txt")
    capture = action_file(
        WORK, f"{shot.name}.txt",
        f"savebin {files['screen']} ${image_base + smoke.SCREEN_BASE:x} ${smoke.SCREEN_BYTES:x}",
        *(f"savebin {files[probe.label]} ${image_base + probe.offset:x} ${probe.size:x}"
          for probe in shot.probes),
        f"b VBL > VBL :once :quiet {settle}")
    # `:N` is Hatari's "break on every Nth hit", and it REJECTS an explicit `:1` (2.6.1, measured by
    # `smoke.py` before it was relied on there), so the first arrival carries no count at all.
    count = "" if shot.arrival == 1 else f":{shot.arrival}"
    session.arm(f"b pc = ${pc:x} {count} :once :quiet {capture}")
    return files


def probe_words(files, probe):
    """One probe's dump as a tuple of signed words.

    The dump exists by construction: it is written by the SAME action file as the screen, ahead of
    the settle chain that writes the marker `photograph_the_scene` refuses the scene without.
    """
    return struct.unpack(f">{probe.size // WORD_BYTES}h", files[probe.label].read_bytes())


def render(shot, files):
    """Decode one shot's framebuffer into `out/showcase/<name>.png` and answer its path.

    `st_pixels.decode_planar` REFUSES a slice that would run off the end of what it was handed,
    which is the one guard a picture needs most: a wrong base decodes as pen 0 everywhere, and a
    blank PNG is a plausible-looking file rather than an error.
    """
    screen = files["screen"].read_bytes()
    pens = struct.unpack(f">{smoke.PALETTE_PENS}H", files["pens"].read_bytes())
    path = WORK / f"{shot.name}.png"
    write_png(str(path), SCREEN_WIDTH, SCREEN_ROWS,
              st_pixels.decode_planar(screen, SCREEN_WIDTH, SCREEN_ROWS),
              st_pixels.palette_rgb([pen & smoke.SHIFTER_PEN_MASK for pen in pens]))
    return path


def photograph_the_scene(scene, offsets):
    """Boot the `play` build, press the scene's keys, and answer {shot name: its dumped files}.

    EVERY EXIT SHUTS THE EMULATOR DOWN, including the ones that give up: a Hatari left running after
    a refusal outlives this process and holds the machine's whole state, which the next scene would
    then boot alongside.

    AND THE MACHINE IS GRADED AFTERWARDS, on `smoke.check_machine_health`'s two surfaces — the exit
    status and the run's own log. Every marker file can land and every picture come out plausible on
    a build that bus-errors a moment later, and a gallery published from that run would be pictures
    of a program that crashes (docs/on-target-execution.md, "exit status + log").
    """
    WORK.mkdir(parents=True, exist_ok=True)
    for stale in (smoke.FILE_ANCHOR_BASE, smoke.FILE_SCREEN_DUMP, smoke.FILE_STATE_RECORD):
        (smoke.DISK / "c" / stale).unlink(missing_ok=True)
    session = HeadlessSession(smoke.hatari_arguments(smoke.ours_medium(), None),
                              WORK / f"{scene.name}.log", WORK / f"{scene.name}.fifo", WORK)
    try:
        captured = drive_the_scene(session, scene, offsets)
    finally:
        status = session.close()
    faults = smoke.check_machine_health(status, session.log_path)
    if faults:
        raise SystemExit(f"ERROR: {scene.name}: " + "; ".join(faults))
    return captured


def drive_the_scene(session, scene, offsets):
    """The scene itself, on a session someone else shuts down.

    THE BREAKPOINTS ARE ARMED BEFORE THE KEYS ARE SENT, so no moment can be missed while the host is
    still talking to the debugger — and the entry breakpoint is what tells a key that landed from one
    that was eaten, which is the same race `smoke.press_the_menu_keys` exists for.
    """
    deadline = time.monotonic() + SCENE_DEADLINE_SECONDS
    booted = {}
    anchors = smoke.await_the_anchor_table(session, booted)
    if anchors is None:
        raise SystemExit(f"ERROR: {scene.name}: {booted.get('problem', 'the boot said nothing')}")

    base = text_base(anchors, offsets)
    image_base = anchors[smoke.ANCHOR_IMAGE_BASE]
    captured = {shot.name: arm_the_shot(session, shot, base + offsets[shot.symbol], image_base)
                for shot in scene.shots}
    if scene.keys:
        entered = WORK / f"{scene.name}_entered.bin"
        entered.unlink(missing_ok=True)
        session.arm(f"b pc = ${base + offsets[scene.entry_symbol]:x} :once :quiet "
                    + action_file(WORK, f"{scene.name}_entered.txt",
                                  f"savebin {entered} ${smoke.HW_SHIFTER_MODE:x} $1"))
        if not smoke.await_play_tally(session, anchors[smoke.ANCHOR_PLAY_TALLY],
                                      smoke.TALLY_MENU_OPENS, 1, "waiting for the menu to be drawn",
                                      smoke.MENU_DEADLINE_SECONDS):
            raise SystemExit(f"ERROR: {scene.name}: the menu was never drawn, so no key could be sent")
        if not smoke.press_the_menu_keys(session, entered.is_file,
                                         deadline - time.monotonic(), scene.keys):
            raise SystemExit(f"ERROR: {scene.name}: the keys never reached {scene.entry_symbol} — "
                             f"see {session.log_path}")

    for shot in scene.shots:
        if not await_file(session, captured[shot.name]["done"],
                          f"waiting for {shot.name}", max(deadline - time.monotonic(), 0),
                          smoke.POLL_SECONDS):
            raise SystemExit(f"ERROR: {scene.name}: arrival {shot.arrival} at {shot.symbol} never "
                             f"came, so there is no picture of {shot.name} — see {session.log_path}")
    return captured


def report_the_probes(shot, files):
    """Print what the globals held at the shot's own instruction, and answer them by label."""
    read = {probe.label: probe_words(files, probe) for probe in shot.probes}
    if read:
        print("           " + ", ".join(f"{label} = {values}" for label, values in read.items()))
    return read


def is_deterministic(shot):
    """Whether two invocations must agree on this picture — everything but the slideshow, which
    picks its rooms with XBIOS `Random` off the machine's clock (see this file's header)."""
    return shot not in SLIDESHOW


def check_the_pictures_are_not_blank(shots, pictures):
    """A capture with one colour is a photograph of nothing — `smoke.py`'s own first check.

    It runs over EVERY capture, the slideshow candidate that is not published included: a set where
    all three of those came back blank has a broken image base, not an unlucky `Random()`, and the
    refusal that names the room collision would send a reader after the wrong thing.
    """
    return [f"{shot.name}: the picture holds one colour, so it is a photograph of nothing"
            for shot in shots
            if distinct_colours(pictures[shot.name]) <= smoke.BLANK_COLOUR_COUNT]


def check_the_moments_differ(pictures, probes):
    """The two demo frames and the two room frames must be DIFFERENT moments, not one photographed
    twice — which is what a breakpoint count Hatari read differently than this file thinks would
    otherwise produce, in silence and with two plausible pictures.

    The demo pair is judged on where the GHOST is, because the replay's whole content is the six
    globals one record feeds it. The room pair is judged on the PICTURES, because with the mouse
    still there is nothing to blow the bubble and it sits where the room put it: what moves between
    those two frames is the fans, the ghost's own animation and the bonus bar.
    """
    problems = []
    first, second = probes[DEMO_EARLY.name], probes[DEMO_LATE.name]
    if first[GHOST_POSITION.label] == second[GHOST_POSITION.label]:
        problems.append(f"{DEMO_EARLY.name} and {DEMO_LATE.name} both have the ghost at "
                        f"{first[GHOST_POSITION.label]}, so they are one moment photographed twice")
    if same_picture(pictures[ROOM_START.name], pictures[ROOM_BUSY.name]):
        problems.append(f"{ROOM_START.name} and {ROOM_BUSY.name} are the same picture, so nothing "
                        f"turned in {ROOM_LATER_FRAME - ROOM_FIRST_DRAWN_FRAME} room frames and the "
                        f"later one is not a later moment")
    if probes[ROOM_BUSY.name][IN_ROOM.label] == (0,):
        problems.append(f"the room had already ended at frame {ROOM_BUSY.arrival}: "
                        f"{ROOM_BUSY.name} is a picture of a room being left, not of one being played")
    hall_room = probes[HALL.name][ROOM_NUMBER.label]
    if hall_room != (HALL_BACKDROP_ROOM,):
        problems.append(f"{HALL.name} was photographed with room {hall_room[0]} on the screen and "
                        f"the hall of fame's backdrop is room {HALL_BACKDROP_ROOM}: this is some "
                        f"other caller of {HALL.symbol}, not the hall's idle loop")
    return problems


def the_two_rooms_to_publish(probes):
    """The first pair of slideshow candidates that drew different rooms, as [(shot, room), ...].

    Answers an EMPTY list when all three drew one room — a one-in-34 coincidence per pair rather
    than a fault, so the caller reports it beside whatever else the run found instead of exiting on
    it and hiding the rest.
    """
    seen = [(shot, probes[shot.name][ROOM_NUMBER.label][0]) for shot in SLIDESHOW]
    for later in seen[1:]:
        if later[1] != seen[0][1]:
            return [seen[0], later]
    return []


def picture_digests(shots, pictures):
    """The sha256 of every DETERMINISTIC picture, by name — what the manifest below is made of."""
    return {shot.name: hashlib.sha256(pictures[shot.name].read_bytes()).hexdigest()
            for shot in shots if is_deterministic(shot)}


def check_against_the_manifest(digests):
    """Compare this run's deterministic pictures against the ones a previous invocation stored.

    THIS IS THE PAIR CHECK, spread over two invocations rather than doubled inside one: a picture
    here costs a whole Hatari boot. It only READS — `publish` writes the manifest, and only once
    everything has passed, so a failing run leaves the baseline it failed against intact. (The
    durable comparison is git's: the published PNGs are tracked, so a picture that moved also shows
    up as a modified file. This manifest is what makes the run itself refuse.)
    """
    if not MANIFEST.is_file():
        print("   no stored manifest: this is the first run, and the next one is the pair check")
        return []
    stored = dict(line.split() for line in MANIFEST.read_text().splitlines() if line.strip())
    return [f"{name}: this picture is deterministic and its sha256 moved (was {stored[name][:12]}, "
            f"is {digest[:12]}) — if the .PRG really draws something else now, delete "
            f"{MANIFEST} and run again"
            for name, digest in sorted(digests.items())
            if name in stored and stored[name] != digest]


def publish(gallery, pictures, digests):
    """Copy the run's pictures into `assets/bubbleghost/` and store the manifest they passed with.

    THE PUBLISHED NAME IS THE GALLERY SLOT, not the capture's: the slideshow's two slots are filled
    by whichever candidates drew different rooms, and the READMEs point at the slots. Publishing
    under a candidate's own name would leave one slot holding a picture from an earlier run.
    """
    ASSETS.mkdir(parents=True, exist_ok=True)
    for slot, shot in sorted(gallery):
        published_path = ASSETS / f"{slot}.png"
        shutil.copy(pictures[shot.name], published_path)
        print(f"   {published_path.relative_to(REPO)}  {published_path.stat().st_size} B")
    MANIFEST.write_text("".join(f"{name} {digest}\n" for name, digest in sorted(digests.items())))


def keys_as_scancodes(keys):
    """The scene's keys as the hex scancodes `hatari-event` is handed, for the run's own report."""
    return " ".join(f"${scancode:02x}" for scancode in keys)


def main():
    smoke.require_gemdos_tos(smoke.TOS_ROM)
    smoke.stage_the_play_prg()
    offsets = elf_offsets()          # one `nm` for the whole run: the four boots share one build
    pictures, probes = {}, {}
    for scene in SCENES:
        print(f"-- {scene.name}: {len(scene.shots)} picture(s), "
              f"{'no keys' if not scene.keys else 'keys ' + keys_as_scancodes(scene.keys)}")
        captured = photograph_the_scene(scene, offsets)
        for shot in scene.shots:
            pictures[shot.name] = render(shot, captured[shot.name])
            probes[shot.name] = report_the_probes(shot, captured[shot.name])
            print(f"   [shot ] {shot.name}: {shot.why}")

    every_shot = [shot for scene in SCENES for shot in scene.shots]
    digests = picture_digests(every_shot, pictures)
    slideshow = the_two_rooms_to_publish(probes)
    print("-- the slideshow drew rooms "
          + (", ".join(str(room) for _, room in slideshow) or "one room only")
          + " this run (XBIOS `Random`, so they are this invocation's and not a promise)")

    problems = (check_the_pictures_are_not_blank(every_shot, pictures)
                + check_the_moments_differ(pictures, probes)
                + check_against_the_manifest(digests))
    if not slideshow:
        problems.append(f"all {len(SLIDESHOW)} slideshow candidates drew the same room, so there is "
                        f"no pair of different rooms to publish — run this again")
    for problem in problems:
        print(f"   [red  ] {problem}")
    if problems:
        print(f"-- FAILED: {len(problems)} problem(s); nothing was published")
        return 1

    gallery = ([(shot.name, shot) for shot in every_shot if shot not in SLIDESHOW]
               + [(slot, shot) for slot, (shot, _) in zip(SLIDESHOW_SLOTS, slideshow)])
    publish(gallery, pictures, digests)
    print(f"-- OK: {len(gallery)} picture(s) in {ASSETS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
