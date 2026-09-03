"""WHAT ONE FRAME COSTS, ROUTINE BY ROUTINE — the original's 68000 code against ours, on the SAME
staged frame, on one instrument.

`profile.py` measures the game as it runs, over a window, under Hatari; it is the right instrument
for a cadence and the wrong one for a routine, because two runs never hold the same game state and
an averaged row hides the frames a player actually feels. This asks the other question:

    given ONE image — a real frame the original itself produced — what does each routine cost on
    each side?

Both sides run under Musashi, cycle-accurate, over identical memory:

  * the ORIGINAL: its own machine code, `emu.run` from the routine's entry in ../../names.txt to
    its `rts` (or to the next slice's entry, for the frame's fall-through stages).
  * OURS: the C cores cross-compiled to m68k — `atari/build/zynaps.elf`, the exact code inside
    ZYNAPS.PRG, asm twins and all — loaded into a Musashi buffer at their link addresses and
    entered through `emu.run_bench`. This is the instrument
    `projects/buggyboy/recreate/tools/bench_frame.py` established; nothing here is new but the game.

**THE POINT IS THE HEAVY FRAME.** `atari/census.py` walks the oracle playing the real game and
saves the busiest image it sees — the entity table's eleven actor slots all live. A tier whose cost
scales with entity count is understated by every average ever taken of it, so each staged frame is
named on the command line and the header says how loaded it was. Give it two (a heavy frame and a
quiet one) and the pair is the scaling evidence.

Usage (census first, then price what it saved):
    python3 atari/census.py 0 300 0 atari/out/heavy.img atari/out/light.img     # stage a busy frame first
    python3 atari/bench_tier.py atari/out/heavy.img [more.img]  # ...then price it, both sides

THE FRAME'S FIFTH SLICE IS NOT HERE, and that is a property of the slice rather than an omission:
`frame_resolve_hits_and_game_state` holds the frame's two synchronisation spins, which the oracle
releases from a schedule and the target build polls from real hardware, so the two sides are not
running the same thing. It is also the one slice already transcribed and shipped (wave C), at
1.02x-1.04x. `src/asm/README.md`, "What wave C added", is the long version.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE.parent                                       # .../projects/zynaps/recreate
sys.path.insert(0, str(REC.parents[2] / "tools"))       # reverse/tools — the shared recreate kit
sys.path.insert(0, str(REC / "test"))
sys.path.insert(0, str(HERE))                          # ...and atari/, for smoke.py

from recreate_kit import project                        # noqa: E402
project.load(REC)                                       # binds the kit's loader/emu to this game

import emu                                              # noqa: E402
import harness                                          # noqa: E402  (loads the .so the kit binds)
import smoke                                            # noqa: E402  (the clock and the image size)
import test_frame as F                                  # noqa: E402

# ---- the two images -----------------------------------------------------------------------------
# The differential's image is 1 MiB and the target's `.bss` one is half that
# (atari/shim_include/os.h's `ZY_TARGET_IMAGE_BYTES`); everything the game's world holds is below
# the smaller of the two, which is why a staged world can be handed to the target build at all.
# `smoke.py` already reads it out of that header, so this takes ITS value rather than running the
# same scrape a second time on the same file.
TARGET_IMAGE_BYTES = smoke.TARGET_IMAGE_BYTES
IMAGE_ALIGN = 256                                       # atari/zynaps_main.c's IMAGE_ALIGN
RECON_STACK_BYTES = 0x40000                             # room above the image for the C call frames

RECON_ELF = HERE / "build" / "zynaps.elf"
RECON_BIN = HERE / "build" / "zynaps.bin"
BUILD_HINT = f"{RECON_ELF} missing — build it: bash atari/build.sh game"
# nm's letters for a symbol that HAS an address — text, data and bss, global (upper) and file-local
# (lower) alike. `g_image_store` is a file-local 'b', so the lower half is not optional here.
# `atari/profile.py`'s NM_SYMBOL_TYPES is the same set for the same reason; it is not imported
# because `import profile` would seize the standard library's module name for the whole process
# (measured: it makes `python3 -m cProfile atari/bench_tier.py` die in cProfile's own import).
NM_ADDRESS_TYPES = "TtDdBb"

# The frame rate and the release period are `smoke.py`'s, which pins the second against
# ../include/irq.h's RASTER_PHASE_PERIOD. Spelling either again here would be the same value in two
# files that import each other, which is exactly what that pin exists to stop — `profile.py` says
# so at its own copy of these two lines.
#
# CPU_HZ IS THIS FILE'S OWN AND IS DELIBERATELY NOT `profile.CYCLES_PER_VBL`. That constant is the
# PAL VIDEO frame, 512 x 313 = 160,256 cycles, which is what a Hatari reading has to be divided by
# because Hatari counts in it. Musashi counts the 68000's own cycles against no video clock at all,
# so the honest denominator here is the nominal 8 MHz second — 160,000 a vblank. The two differ by
# 0.16%, which moves no column of the table below, and calling them one value would make a Musashi
# figure claim a precision about the ST's video clock that it does not have.
CPU_HZ = 8_000_000                                      # stock Atari ST 68000
VBL_HZ = smoke.VBL_HZ
# One release slot. The frame loop is let go on every SECOND vertical blank (atari/profile.py says
# why), so this — not a vblank — is the budget a frame either fits or misses, and the only
# denominator a "how much of the frame is this?" column can honestly use.
RELEASE_SLOT_CYCLES = CPU_HZ // VBL_HZ * smoke.PACING_RELEASE_PERIOD_VBLS

# ---- the entity table, as the census reads it ---------------------------------------------------
# EVERY RECORD CONSTANT IS `test_frame`'S, imported and not respelt. Its MIRRORS pin each one
# against the header that owns it (include/player.h, include/entity.h, include/frame.h); a copy
# here would be a second, unpinned spelling that `0x14` and `20` could drift apart under, and this
# instrument and the suite that reads its frames would then disagree about which slots are live.
#
# The eleven records the per-frame actor passes walk: the three enemy shot slots, then the eight
# wave slots. BUILT FROM `test_frame`'s three names rather than written down as 6 and 16, because a
# ninth wave slot in include/enemy.h would fail ENEMY_SLOT_COUNT's mirror loudly and leave a bare
# `16` here pricing ten actors of eleven in silence.
ACTOR_FIRST_SLOT = F.ENEMY_SHOT_SLOT_FIRST
ACTOR_LAST_SLOT = F.ENEMY_SLOT_FIRST + F.ENEMY_SLOT_COUNT - 1
A_actor_move_table = 0x19380                            # include/enemy.h
A_actor_anim_table = 0x193dc
JUMP_TABLE_ENTRY_BYTES = 4
ACTOR_HANDLER_TYPE_MAX = 0x32                           # the `cmpi.b #$32` both passes share

# ---- what to price -------------------------------------------------------------------------------
# (label, the original's entry, the original's entry registers, the original's stop PC or None for
#  its own rts, our symbol, our extra stack arguments past the image).
#
# A stage of the frame loop FALLS THROUGH into the next rather than returning, so its span is named
# by the next slice's entry; a routine ends at its own `rts` and stops there. The head slice has TWO
# fall-through exits and `_head_stop` picks the one this image takes.
#
# "carried" marks the two arguments the spawn stage takes that no instruction of the frame wrote —
# test_frame.carried_registers is where a case gets them, and this table asks it for the same pair
# rather than restating the probe. "chance" is the first of that pair alone, in D1.
# The markers a row uses for an argument the frame CARRIES rather than holds in a global. Each is
# resolved once per image by `_entry_regs` / `_our_args` against what the oracle really held.
CARRIED, CHANCE, CHANCE_D1 = "carried", "chance", "chance_d1"
# ...and the drone/fire stage's own pair, which is a different pair entirely: `include/frame.h`
# gives it the SHIP RECORD in %a2 and the joystick byte in %d0. Passing the spawn stage's
# (chance, ground_y) here made both shores bail on a record at 0x7f — a 256-cycle "stage" that this
# table reported as real and folded into its total until the review caught it.
SHIP_AND_STICK, SHIP_AND_STICK_REGS = "ship_and_stick", "ship_and_stick_regs"

FN_asteroids_draw = 0x159be
# The two the per-handler tables below key on, named because the script-VM row also
# selects on them and a bare 0x14c16 in that comprehension says nothing.
FN_enemy_move_scripted = 0x14c16
FN_actor_script_run = 0x14c66

STAGES = [
    ("frame_panel_scroll_and_ship_stage", F.ENTRY_FRAME_HEAD, {}, "head",
     "g_frame_panel_scroll_and_ship_stage", ()),
    ("frame_drone_and_fire_stage", F.ENTRY_DRONE_AND_FIRE, SHIP_AND_STICK_REGS,
     F.ENTRY_SPAWN_AND_MOVE, "g_frame_drone_and_fire_stage", SHIP_AND_STICK),
    ("frame_spawn_and_move_stage", F.ENTRY_SPAWN_AND_MOVE, {}, F.ENTRY_DRAW_AND_COLLIDE,
     "g_frame_spawn_and_move_stage", CARRIED),
    ("frame_draw_objects_and_collide", F.ENTRY_DRAW_AND_COLLIDE, {}, F.ENTRY_RESOLVE,
     "g_frame_draw_objects_and_collide", ()),
]

# The enemy/actor/projectile tier, each routine entered on its own. Every one of these is called
# from inside a stage above, so the two tables measure some of the same cycles twice on purpose: the
# stage rows say how big the prize is and the tier rows say where in it.
TIER = [
    ("enemies_move_all", 0x1487c, {}, None, "g_enemies_move_all", ()),
    ("enemies_animate_all", 0x147f2, {}, None, "g_enemies_animate_all", ()),
    ("enemy_fire_and_update_shots", 0x11906, CHANCE_D1, None,
     "g_enemy_fire_and_update_shots", CHANCE),
    ("player_shot_update_all", 0x152a4, {}, None, "g_player_shot_update_all", ()),
    ("explosion_animate_all", 0x1544e, {}, None, "g_explosion_animate_all", ()),
    ("anim_ground_objects", 0x14626, {}, None, "g_anim_ground_objects", ()),
    ("asteroids_move", 0x159f2, {}, None, "g_asteroids_move", ()),
    ("asteroids_animate", 0x15a6a, {}, None, "g_asteroids_animate", ()),
    ("asteroids_draw", FN_asteroids_draw, {}, None, "g_asteroids_draw", ()),
    ("screen_flip_buffers", 0x1297a, {}, None, "g_screen_flip_buffers", ()),
]

# The per-actor handlers the two passes dispatch to, by the address the image's own jump table
# holds. A row is priced once per LIVE actor that dispatches to it and reported as the sum, which is
# what that handler costs the frame — the shape that scales with the entity count.
ACTOR_HANDLERS = {
    0x1494a: "g_enemy_move_type14_sine",
    0x1499e: "g_enemy_move_type16_left",
    0x149d2: "g_enemy_move_type15_dive",
    FN_enemy_move_scripted: "g_enemy_move_scripted",
    0x14ec4: "g_enemy_move_type17_left",
    0x14730: "g_anim_enemy_type12",
    0x1476e: "g_anim_enemy_type14",
    0x147ac: "g_anim_enemy_type15_diving",
    0x1483e: "g_anim_enemy_type17",
    0x1467e: "g_anim_enemy_type20",
    0x146ba: "g_anim_enemy_type22",
    0x146f6: "g_anim_enemy_type16",
    0x1530e: "g_enemy_set_sprite_b",
    0x15332: "g_enemy_anim_puff_b",
}
# ...and the script VM underneath the scripted mover, priced the same way.
SCRIPT_VM = {FN_actor_script_run: "g_actor_script_run"}

# ---- the draw / collide stage, taken apart ------------------------------------------------------
# Its two halves are a sprite pass over all twenty entity slots and an ALL-PAIRS collision walk, and
# only the second scales with the square of what is on screen. Neither has an entry point of its own
# on our side, so the stage is priced by measuring each PART on both sides and reporting the stage
# minus the parts as the loop-and-glue remainder — which is exactly where a per-call trampoline the
# original does not have would show up.
FN_draw_sprite_masked_collide = 0x15b7c
FN_object_pair_overlap_mark = 0x11cce


def be32(image, at):
    return int.from_bytes(image[at:at + 4], "big")


def live_slots(image):
    return [slot for slot in range(F.ENTITY_SLOTS)
            if image[F.entity_record(slot) + F.ENTITY_ALIVE]]


# The row label of the stage the head slice may branch past, and the note a skipped row carries.
# `_head_stop` decides for a given image; the frame itself does exactly the same test.
SKIPPABLE_STAGE = "frame_drone_and_fire_stage"
SKIPPED = "not run: the head slice branched past it on this frame"


def _head_stop(image):
    """Which of the head slice's two fall-through exits this image takes (test_frame's own gate)."""
    return F.ENTRY_DRONE_AND_FIRE if F._stage_head_falls_through(image) else F.ENTRY_SPAWN_AND_MOVE


def _rows_this_frame_runs(rows, state):
    """`rows` minus any stage the frame's own gates skip over.

    A stage entered from outside its own control flow still executes SOMETHING — 256 cycles of the
    original's, on a frame where the ship is dead — and reporting that as the stage's cost, and
    summing it into the frame's total, is a measurement of a thing that did not happen.
    """
    if F._stage_head_falls_through(state):
        return rows, []
    return ([row for row in rows if row[0] != SKIPPABLE_STAGE],
            [row[0] for row in rows if row[0] == SKIPPABLE_STAGE])


def actor_dispatch(image, table):
    """[(handler address, actor record)] for every live actor this pass would run, in slot order.

    The guard is the original's own — alive, and a SIGNED type below 0x32 — so a table built here
    holds exactly the calls the pass makes, and a handler with no live actor gets no row rather than
    a zero one.
    """
    out = []
    for slot in range(ACTOR_FIRST_SLOT, ACTOR_LAST_SLOT + 1):
        record = F.entity_record(slot)
        if not image[record + F.ENTITY_ALIVE]:
            continue
        raw_type = image[record + F.ENTITY_TYPE]
        # SIGNED, as the original's `cmpi.b #$32` + `bge` is: a type with bit 7 set is NEGATIVE
        # and so is DISPATCHED, not skipped. An unsigned test here would drop exactly those from
        # the table, and the staged frames' types (0x0c/0x14/0x64) would never have said so.
        signed_type = raw_type - 0x100 if raw_type >= 0x80 else raw_type
        if signed_type >= ACTOR_HANDLER_TYPE_MAX:
            continue
        out.append((be32(image, table + raw_type * JUMP_TABLE_ENTRY_BYTES), record))
    return out


def _symbols():
    """name -> link address, out of the cross-compiled game ELF.

    ONLY THE SYMBOLS THAT HAVE AN ADDRESS, and that filter is the whole of what this has to get
    right. nm also prints every twin's `.equ` names as ABSOLUTES ('a') — and 24 of those repeat in
    this ELF, because several `.S` files each export the same header constant on purpose. Those are
    VALUES, not addresses. Letting them into a last-wins dict is the one way a lookup here can
    silently resolve to the wrong thing: an `.equ` that happened to share a routine's name would
    shadow it, and `shipped_symbol` below would price a routine the game does not run.

    NO DUPLICATE-NAME REFUSAL on top of that, deliberately, and `atari/profile.py`'s `symbol_map`
    is where to read what one looks like. Every name asked of this map is a `.globl`, and two of
    those in one linked executable is a link error; the file-local `t`/`b` names that CAN legally
    repeat (two translation units with a same-named `static`) are never looked up here, so refusing
    them would stop the bench over a build that is perfectly good.
    """
    if not (RECON_ELF.exists() and RECON_BIN.exists()):
        raise SystemExit(BUILD_HINT)
    syms = {}
    for line in subprocess.check_output([smoke.NM, str(RECON_ELF)], text=True).splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1] in NM_ADDRESS_TYPES:
            syms[fields[2]] = int(fields[0], 16)
    return syms


def _load_recon(syms):
    """The recon's memory: text+data at their link addresses, its image array, a stack and a
    sentinel above both. Returns (mem_template, image_addr, stack_top, sentinel)."""
    image_addr = (syms["g_image_store"] + IMAGE_ALIGN - 1) & ~(IMAGE_ALIGN - 1)
    stack_top = (image_addr + TARGET_IMAGE_BYTES + RECON_STACK_BYTES) & ~0xf
    sentinel = stack_top + 0x1000                                    # even, above the stack
    mem = bytearray(sentinel + 0x1000)
    mem[0:RECON_BIN.stat().st_size] = RECON_BIN.read_bytes()
    # The target's own pointer to that array. The tier's cores take the image as an argument and
    # never read this, but the video door does, and a run that left it 0 would fault there rather
    # than measure anything.
    at = syms["zy_image_base"]
    mem[at:at + 4] = image_addr.to_bytes(4, "big")
    return mem, image_addr, stack_top, sentinel


def _entry_regs(regs, carried, joystick):
    """The original's entry register file for one row, resolving the carried-argument markers."""
    if regs == CHANCE_D1:
        return {"d1": carried[0]}
    if regs == SHIP_AND_STICK_REGS:
        return {"a2": F.A_PLAYER_RECORD, "d0": joystick}
    return dict(regs)


def _our_args(extra, carried, joystick):
    """...and our core's stack arguments past the image, resolving the same markers."""
    if extra == CARRIED:
        return carried
    if extra == CHANCE:
        return (carried[0],)
    if extra == SHIP_AND_STICK:
        return (F.A_PLAYER_RECORD, joystick)
    return extra


def measure_original(state, rows, carried):
    """{label: (insns, cycles)} for the ORIGINAL's own code over `state`."""
    out = {}
    joystick = state[F.A_JOYSTICK_STATE]
    for label, entry, regs, stop, _sym, _args in rows:
        stop_pc = _head_stop(state) if stop == "head" else (stop or 0)
        try:
            _final, _writes, r = emu.run(bytearray(state), entry,
                                         _entry_regs(regs, carried, joystick),
                                         stop_pc=stop_pc, max_insns=F.FRAME_MAX_INSNS)
        except RuntimeError as exc:
            out[label] = exc
            continue
        out[label] = (r["ninsns"], r["cycles"])
    return out


def shipped_symbol(glue, syms):
    """The symbol the GAME calls for this routine, and its name for the table.

    A twinned core is substituted at its CALL SITE through a `ZY_*()` seam, so the `g_*` glue still
    names the C — which means pricing the glue would price the routine the target does not run. A
    twin that SHIPS is in the linked ELF under `<core>_asm`; one that is verification-only had its
    object dropped from the link, so it is absent and the C is the right answer for it.

    **THIS IS PRESENCE, NOT REACHABILITY, AND THE DIFFERENCE MATTERS IN EXACTLY ONE CASE.** If a
    call site lost its `ZY_FRAME()` wrapper the twin would still be defined and exported, and this
    would price the twin for a routine the game runs as C. `atari/build.sh`'s asm-twin gate is what
    catches that — it asks the OBJECTS whether a core object still references the bare C core — and
    it is the authority; this is a convenience that agrees with it whenever the build is green. Run
    the build before trusting a `[twin]` marker.
    """
    core = glue[len("g_"):] if glue.startswith("g_") else glue
    twin = core + "_asm"
    return (twin, True) if twin in syms else (glue, False)


def measure_ours(state, rows, carried, recon, syms):
    """{label: (insns, cycles)} for OUR cross-compiled cores over the same `state`."""
    joystick = state[F.A_JOYSTICK_STATE]
    for label, _entry, _regs, _stop, glue, extra in rows:
        sym, _is_twin = shipped_symbol(glue, syms)
        if sym not in syms:
            yield label, KeyError(f"{sym} is not in {RECON_ELF.name}")
            continue
        try:
            yield label, run_ours(state, syms[sym], _our_args(extra, carried, joystick), recon)
        except RuntimeError as exc:
            yield label, exc


def run_ours(state, entry, args, recon):
    """One run of one of our cores at `entry`, over a fresh copy of the staged image."""
    mem_template, image_addr, stack_top, sentinel = recon
    mem = bytearray(mem_template)
    mem[image_addr:image_addr + TARGET_IMAGE_BYTES] = state[:TARGET_IMAGE_BYTES]
    # run_bench writes the return address at sp and the image at sp+4; the m68k SysV ABI puts every
    # further argument in the longwords above it, which is what this fills in.
    for i, value in enumerate(args):
        at = stack_top + 8 + 4 * i
        mem[at:at + 4] = (value & 0xFFFFFFFF).to_bytes(4, "big")
    r = emu.run_bench(mem, entry, arg0=image_addr, sp=stack_top, sentinel=sentinel)
    return r["ninsns"], r["cycles"]


def per_actor_rows(state, dispatch, names, syms, recon):
    """[(label, ours, original)] — one row per handler, summed over the live actors that reach it."""
    rows = {}
    for handler, record in dispatch:
        name = names.get(handler)
        if name is None:
            continue
        _final, _writes, r = emu.run(bytearray(state), handler, {"a2": record},
                                     max_insns=F.FRAME_MAX_INSNS)
        ours = run_ours(state, syms[name], (record,), recon)
        was = rows.setdefault(name, [0, 0, 0])
        was[0] += ours[1]
        was[1] += r["cycles"]
        was[2] += 1
    return [(f"{name} x{count}", (count, ours), (count, orig))
            for name, (ours, orig, count) in sorted(rows.items())]


def draw_stage_parts(state, syms, recon, already_measured):
    """[(label, ours, original)] for the draw/collide stage's measurable parts, then the remainder.

    The pair walk's calls depend on which entities the SPRITE pass marked, so the pairs are
    enumerated over the image as it stands after that pass — the original's own, run to
    SPRITE_PASS_END_PC — rather than over the image the stage started from.

    **READ THE REMAINDER ROW ONLY WHILE THE STAGE IS C.** Every "part" here is priced by calling
    that part's own C core standalone, which is what the stage does while it is C. Once the stage is
    an asm TWIN those parts are no longer separately callable — `object_pair_overlap_mark` is
    transcribed INSIDE the twin and costs the original's 11,040 there, not the C core's 15,520 this
    row still measures — so the subtraction over-charges the parts and the remainder comes out
    absurdly low (measured: 4,210 against the original's 7,902, a "0.53x" that is an artefact of the
    arithmetic and not a routine that got faster than the original). The WHOLE-STAGE row at the foot
    is exact either way and is the one to quote; this breakdown is a diagnosis of where a C stage's
    excess lives, and it did its job before the twin existed.
    """
    rows = []
    # The STAGES table above already clocked this stage on both sides, and it is the heaviest
    # measurement the tool makes — re-running it here cost two more full executions of it per image.
    stage_ours, stage_orig = already_measured
    measured_ours = measured_orig = 0

    def part(label, our_symbol, original_entry, calls, our_args, original_regs):
        """One part of the stage, summed over the calls the stage makes to it."""
        nonlocal measured_ours, measured_orig
        ours = orig = 0
        for call in calls:
            ours += run_ours(state, syms[our_symbol], our_args(call), recon)[1]
            _f, _w, r = emu.run(bytearray(state), original_entry, original_regs(call),
                                max_insns=F.FRAME_MAX_INSNS)
            orig += r["cycles"]
        rows.append((f"{label} x{len(calls)}", (len(calls), ours), (len(calls), orig)))
        measured_ours += ours
        measured_orig += orig

    part("asteroids_draw", "asteroids_draw", FN_asteroids_draw,
         [None], lambda _call: (), lambda _call: {})

    drawn = live_slots(state)
    part("draw_sprite_masked_collide (the twin)", "draw_sprite_masked_collide_asm",
         FN_draw_sprite_masked_collide, drawn,
         lambda slot: (F.entity_record(slot), F.entity_record(slot) + F.ENTITY_PIXEL_HIT),
         lambda slot: {"a2": F.entity_record(slot)})

    after_sprites, _writes, _regs = emu.run(bytearray(state), F.ENTRY_DRAW_AND_COLLIDE, {},
                                            stop_pc=F.SPRITE_PASS_END_PC, max_insns=F.FRAME_MAX_INSNS)
    pairs = F.pixel_hit_pairs(after_sprites)
    part("object_pair_overlap_mark", "object_pair_overlap_mark",
         FN_object_pair_overlap_mark, pairs,
         lambda pair: (F.entity_record(pair[0]), F.entity_record(pair[1]),
                       F.collision_row(pair[0]), F.collision_row(pair[1]), pair[0], pair[1]),
         lambda pair: {"a2": F.entity_record(pair[0]), "a1": F.entity_record(pair[1]),
                       "a3": F.collision_row(pair[0]), "a4": F.collision_row(pair[1]),
                       "a5": pair[0], "a6": pair[1]})

    twinned = shipped_symbol("g_frame_draw_objects_and_collide", syms)[1]
    remainder = "...the loops and glue [ARTEFACT: see the docstring]" if twinned \
        else "...the stage's own loops and call glue"
    rows.append((remainder,
                 (0, stage_ours[1] - measured_ours), (0, stage_orig[1] - measured_orig)))
    rows.append(("frame_draw_objects_and_collide" + NOT_IN_THE_TOTAL, stage_ours, stage_orig))
    return rows


def _row(label, ours, original):
    if not isinstance(ours, tuple) or not isinstance(original, tuple):
        why = original if not isinstance(original, tuple) else ours
        print(f"  {label:<40}{'—':>11}{'—':>11}{'':>9}{'':>10}   {type(why).__name__}: {why}")
        return 0, 0
    if original[1] == 0:
        # A part the stage never reached on this frame — no calls, so no ratio to report and
        # nothing to add to the totals. Printed rather than dropped: "x0" IS the reading on a
        # quiet frame, and a silently missing row would read as a tool that failed.
        print(f"  {label:<40}{ours[1]:>11,}{original[1]:>11,}{'—':>9}{ours[1]:>+10,}"
              f"{100 * ours[1] / RELEASE_SLOT_CYCLES:>8.1f}%")
        return 0, 0
    print(f"  {label:<40}{ours[1]:>11,}{original[1]:>11,}{ours[1] / original[1]:>8.2f}x"
          f"{ours[1] - original[1]:>+10,}{100 * (ours[1] - original[1]) / RELEASE_SLOT_CYCLES:>8.1f}%")
    return ours[1], original[1]


# A row whose cycles are already counted by another row in the same table — the draw/collide
# breakdown ends with the WHOLE stage, which is the sum of the rows above it. Summing it too made
# that table's TOTAL exactly twice the stage.
NOT_IN_THE_TOTAL = ", whole"


def _table(title, rows):
    print(f"\n{title}")
    print(f"  {'routine':<40}{'ours':>11}{'original':>11}{'ratio':>9}{'delta':>10}{'% slot':>9}")
    total_ours = total_orig = 0
    for label, ours, original in rows:
        u, o = _row(label, ours, original)
        if label.endswith(NOT_IN_THE_TOTAL):
            continue
        total_ours += u
        total_orig += o
    if total_orig:
        print(f"  {'TOTAL':<40}{total_ours:>11,}{total_orig:>11,}{total_ours / total_orig:>8.2f}x"
              f"{total_ours - total_orig:>+10,}"
              f"{100 * (total_ours - total_orig) / RELEASE_SLOT_CYCLES:>8.1f}%")
    return total_ours, total_orig


def _paired(rows, original, ours, syms):
    """The table's rows, each marked with whether the GAME runs a twin or the C for that routine.

    Marked rather than left to the reader, because the two readings mean opposite things: a 1.04x
    twin row is a transcription's fixed cost and a 2.47x C row is a lever nobody has taken yet.
    """
    return [(label + (" [twin]" if shipped_symbol(glue, syms)[1] else ""),
             ours.get(label), original.get(label))
            for label, _entry, _regs, _stop, glue, _extra in rows]


def price(staged, syms, recon):
    state = bytearray(staged.read_bytes())
    live = live_slots(state)
    actors = [s for s in live if ACTOR_FIRST_SLOT <= s <= ACTOR_LAST_SLOT]
    print(f"\n{'=' * 100}\nthe staged frame: {staged}")
    print(f"  {len(live)} live entities, {len(actors)} of the eleven actor slots — types "
          f"{sorted(state[F.entity_record(s) + F.ENTITY_TYPE] for s in live)}")
    print(f"  one release slot = {RELEASE_SLOT_CYCLES:,} cycles (2 vblanks at {CPU_HZ / 1e6:g} MHz)")

    carried = F.carried_registers(state, F.ENTRY_FRAME_HEAD)
    print(f"  the registers this frame carries into the spawn stage: chance={carried[0]:#x} "
          f"ground_y={carried[1]:#x}")

    stage_cost = {}
    stages, skipped = _rows_this_frame_runs(STAGES, state)
    for name in skipped:
        print(f"  {name}: {SKIPPED}")
    for title, rows in (("THE FRAME'S SPIN-FREE STAGES — the whole prize (the fifth slice is not "
                         "comparable here; see the module docstring)", stages),
                        ("THE ENEMY / ACTOR / PROJECTILE TIER, inside those stages", TIER)):
        original = measure_original(state, rows, carried)
        ours = dict(measure_ours(state, rows, carried, recon, syms))
        stage_cost.update({label: (ours.get(label), original.get(label)) for label, *_r in rows})
        _table(title, _paired(rows, original, ours, syms))

    move_pass = actor_dispatch(state, A_actor_move_table)
    for title, dispatch in (
            ("THE MOVE PASS, BY HANDLER — summed over the live actors that reach each", move_pass),
            ("THE ANIMATION PASS, BY HANDLER — the same, for the other jump table",
             actor_dispatch(state, A_actor_anim_table))):
        _table(title, per_actor_rows(state, dispatch, ACTOR_HANDLERS, syms, recon))

    _table("THE DRAW / COLLIDE STAGE, TAKEN APART — the parts are measured, the remainder is the "
           "stage minus them",
           draw_stage_parts(state, syms, recon, stage_cost["frame_draw_objects_and_collide"]))

    _table("THE SCRIPT VM, under the scripted mover",
           per_actor_rows(state, [(FN_actor_script_run, record) for handler, record in move_pass
                                  if handler == FN_enemy_move_scripted],
                          SCRIPT_VM, syms, recon))


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python3 atari/bench_tier.py <staged.img> [more.img ...]")
    syms = _symbols()
    recon = _load_recon(syms)
    for path in sys.argv[1:]:
        price(Path(path), syms, recon)


if __name__ == "__main__":
    main()
