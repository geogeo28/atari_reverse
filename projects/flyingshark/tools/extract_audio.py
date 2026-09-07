#!/usr/bin/env python3
"""Dump Flying Shark's (Atari ST, Firebird 1988) music and sound effects.

Usage:
  python3 projects/flyingshark/tools/extract_audio.py [OUT_DIR]

OUT_DIR defaults to `projects/flyingshark/out/audio` (gitignored). Reads only the game's own files
under `projects/flyingshark/bin/` — FLYSHARK.PRG and the sound driver it loads, `disk/A/MODULE.BAK`
— and writes, for each of the driver's 5 tunes and 13 sound effects:

  mus_N.ym  / mus_N.wav     one tune, 0..4
  sfx_NN.ym / sfx_NN.wav    one effect, 00..12. Effect 12 is in the FILE but is not reachable in the
                            shipped game: no call site starts it (the six `sfx_start` sites in
                            out/prg_dis.txt load 6, 10, 5, 2, 5 and 11), and on the real machine the
                            last 8 bytes of its record are gone — the module's staged bytes end at
                            0x5998c and `clear_actor_arrays` (0x115e2) zeroes the entity arena from
                            0x59984. It is captured from the pristine file, which IS the file's
                            content, and the manifest's game_event column says so.
  mix_mus1_sfx05.ym / .wav  ONE combined example: tune 1 with effect 5 started at frame 100, which
                            is the manifest's evidence that an effect takes channel C and leaves
                            channels A and B — their periods, their volumes, their four mixer gate
                            bits and the noise period all three share — exactly as the tune left
                            them (`check_sfx_preempts_channel_c`)
  manifest.tsv              per track: kind, number, frames, seconds, how the capture ended, the
                            loop it proved, how many frames are audible, the render's peak, and the
                            game event that starts that number

`manifest.tsv` is written LAST and only after every check below has passed, so its presence is what
marks the directory complete: a run that fails leaves the .ym/.wav files it got to and no manifest.

THIS IS AN ORACLE-DRIVEN CAPTURE, NOT A STATIC PARSE. Flying Shark's whole audio API is four entry
points in one 4 KB position-independent module (`notes/sound_engine.md`), and rather than
re-implement its sequencer this tool runs the ORIGINAL 68000 code under the kit's Musashi oracle
(`tools/recreate_kit`) and records what it writes to the chip:

  music_start / sfx_start   once, with `d0.b` = the number and `a0` = the module's TEXT base
  sound_vbl_tick            once per emulated 50 Hz frame -> one frame of PSG traffic

Each tick's `(reg, value)` writes are folded into a running shadow of the chip's 16 registers, and
the shadow is snapshotted after every tick. That snapshot IS a YM frame — a tick that writes nothing
new still yields one, because the chip holds what it was last given. The driver in fact flushes
13 registers on every tick without exception (`TICK_FLUSH_ORDER`, checked per tick), plus register
13 on the ticks that latch an envelope shape.

HOW THE MODULE IS STAGED. `MODULE.BAK` is a GEMDOS .PRG with ABSFLAG set and no relocation table:
genuinely position-independent, so the game does not load it, it *reads* it. Its file-table entry
inside FLYSHARK.PRG names a destination and a length, and this tool reads both out of the relocated
image rather than restating them (`module_staging`) — so the bytes land exactly where and as far as
the game puts them, which is 0x1065 = 4197 of the file's 4198 bytes: the last byte is never read,
and the tool does not read it either. The game then calls the module at destination + 28, adding the
.PRG header length itself, which is why the module's TEXT base is 0x58944 and not 0x58928. There is
no init entry and none is needed: the variable block ships zeroed except `master_volume`, and the
two start entries seed the rest.

NOT CROSS-CHECKED AGAINST THE MACHINE'S OWN PLAYER, and it cannot be yet. `docs/sound.md`'s recipe
for checking a dump is to record the game under Hatari and compare, and Flying Shark's payload does
not survive long enough to play a note: booted from `bin/disk` as C: on TOS 1.04 it draws the title
and then dies (`tools/boot_shots.py`), and a 75 s recording with `--sound 44100` came back digitally
silent from the first sample to the last. So the register streams here have been checked against the
driver (the flush order, the loop replay, the pre-emption claim, silence against the render) and
against nothing outside it. When the payload runs far enough to start a tune, the cross-check is a
recording and a per-frame tone-period comparison against `mus_1`.

THE $ff820a SEED, AND WHY IT IS NOT PASSED AS ONE. The tick reads `$ff820a` (the shifter's sync
byte) once per frame and tests BIT 1: set = a 50 Hz machine, so the tick runs; clear = 60 Hz, and
the driver then drops one tick in six to keep the sequencer at 50 steps per second
(`docs/hardware-map.md`; `notes/sound_engine.md`, "the tick", step 3). The oracle answers an
unseeded hardware read with 0 — the 60 Hz machine — which would stretch every capture by 20 %
against the 50 Hz machine the game shipped for. The seed is therefore *the audio-capture mode's own
machine profile*: `emu.audio_capturing()` installs `emu.hw_capture_profile()`, which declares
`$ff820a = 0x02`, and passing a `hw_seed` alongside it is refused (TRAP_MODEL.md, Phase 7).
`check_tempo_profile` asserts that bit before anything is captured, because getting it wrong is
inaudible in the result — every track would simply be a fifth too slow.

HOW A CAPTURE ENDS, in the order the loop asks:

  ended   the driver cleared its own active flag — `music_active` for a tune (pattern command 0x88,
          "end of song"), `sfx_active` for an effect (its duration counter reached 0).
  loop    the driver's whole mutable state — the variable block plus the three 24-byte channel
          structs — came back to a value it had already held. State is everything the next tick
          reads, so a repeat means the output from here on is bit-for-bit what it was from there
          on, for ever. The file then holds the lead-in plus exactly one period, and its YM6 loop
          field points at the period's first frame. `check_loop_replays` plays the next period out
          and compares it frame by frame rather than trusting the argument.
  capped  neither happened inside TUNE_FRAME_CAP / SFX_FRAME_CAP frames.

WHAT THIS TOOL DELIBERATELY DOES NOT DO:

  * it does not run the GAME. Nothing here boots FLYSHARK.PRG, reads a level or plays a frame; the
    image exists only so the module sits at the address the game's own file table gives it, and so
    that table can be read. Which number the game starts when is `notes/sound_engine.md`'s reading
    of the call sites, carried here as text in `TUNE_EVENTS` / `SFX_EVENTS` and reproduced in the
    manifest — it is not re-derived, and it is the one column no check backs.
  * it does not model the chip. The .wav files come from BuggyBoy's `recreate/sound/ym2149.py`, the
    workspace's one YM2149 synth (`docs/sound.md`), imported rather than copied. They are a
    listening aid; the .ym register stream is the artefact.
  * it does not chase the driver's own `sound_stop` entry, nor the second `music_active` clear the
    game does at 0x121ac. Both silence a track from outside; neither adds a frame to a dump.
  * it captures ONE music+effect combination, not the cross product. Pre-emption is a property of
    the driver (effects own channel C while they run), so one example proves it and 65 would not.
"""
import os
import re
import struct
import sys
from collections import namedtuple

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TOOLS_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(PROJECT_DIR))

RECREATE_DIR = os.path.join(PROJECT_DIR, "recreate")
GAME_PRG = os.path.join(PROJECT_DIR, "bin", "FLYSHARK.PRG")
MODULE_FILE = os.path.join(PROJECT_DIR, "bin", "disk", "A", "MODULE.BAK")
DEFAULT_OUT_DIR = os.path.join(PROJECT_DIR, "out", "audio")

# ---- binding the kit ------------------------------------------------------------------------------
# The kit's oracle modules are bound to a game through that game's `recreate/project.toml`, which is
# the only supported route (recreate_kit/project.py) and which is where the load base, the image size
# and this game's `tos_malloc_unused` waiver are stated once for every tool that drives the binary.
# The capture needs no built candidate library — it drives the ORIGINAL code — and `project.load`
# does not open one, so binding here costs nothing beyond the oracle the run needs anyway.

KIT_ERROR_HELP = ("this capture drives the kit's Musashi oracle and BuggyBoy's YM2149 renderer, and "
                  "one of them is missing (%s):\n"
                  "  make -C projects/flyingshark/recreate oracle\n"
                  "...and run it with the atari_reverse conda env's python (the renderer needs "
                  "numpy).")


def bind_kit():
    """Bind `tools/recreate_kit` to Flying Shark's binary and import the oracle. Idempotent-ish.

    Returns the modules the capture needs. `project.load` is process-global and refuses a rebind, so
    this runs once, at import.
    """
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    from recreate_kit import project

    project.load(RECREATE_DIR)                       # ../recreate/project.toml: the game's binding

    # BuggyBoy's YM2149 synth is the workspace's ONE renderer (docs/sound.md): imported, never
    # copied, so there is one set of DAC and envelope approximations rather than two.
    sys.path.insert(0, os.path.join(REPO_ROOT, "projects", "buggyboy", "recreate", "sound"))
    import emu                                       # noqa: E402  (only bindable after project.load)
    import loader                                    # noqa: E402
    import ym2149                                    # noqa: E402  (BuggyBoy's YM2149 synth)
    import ym_capture                                # noqa: E402  (REPO_ROOT/tools: .ym/.wav)
    from recreate_kit import os_map                  # noqa: E402
    return emu, loader, ym2149, ym_capture, os_map


try:
    emu, loader, ym2149, ym_capture, os_map = bind_kit()
except (OSError, ImportError) as error:              # the ctypes.CDLL behind the oracle, or numpy
    sys.exit(KIT_ERROR_HELP % error)

# ---- the module, as the game stages it -------------------------------------------------------------
# FLYSHARK.PRG's file table is a run of records {longword destination, longword length, NUL-
# terminated "A\\NAME.EXT"}. The destination is an ABSOLUTE address in the relocated image (the
# longword is in the .PRG's relocation table), so the staging below is read out of the game rather
# than restated from the notes — the one thing that could silently put the module at the wrong
# address is the thing the driver would then be entered through.

MODULE_TABLE_ENTRY = 0x16304                         # out/prg_dis.txt: the record for A\MODULE.BAK
MODULE_TABLE_NAME = b"A\\MODULE.BAK\x00"
TABLE_DEST = 0x00                                    # record layout, in the order Fread wants them
TABLE_LENGTH = 0x04
TABLE_NAME = 0x08
TABLE_LONG = ">I"

MODULE_HEADER_BYTES = loader.prg_dis.HEADER_LEN      # the GEMDOS .PRG header the game skips ITSELF:
                                                     # it reads the whole file, then calls dest + 28
PRG_MAGIC = 0x601A
PRG_ABSFLAG_NO_RELOC = 0xFFFF                        # ...which is why the module may be placed raw

# ---- the driver's entry points and variables, at MODULE_BASE ---------------------------------------
# Addresses are out/names_module.txt's, i.e. module TEXT base + the offsets notes/sound_engine.md
# pins against the instruction that reads them. `check_staging_matches_the_game` is what ties this
# base to the game's own `lea $58944.l,a0`.

MODULE_BASE = 0x58944
SOUND_VBL_TICK = 0x5896A                             # +38: one 50 Hz frame
SFX_START = 0x58DF0                                  # +1196: d0.b = effect 0..12
MUSIC_START = 0x58E2C                                # +1256: d0.b = tune 0..4

MUSIC_ACTIVE = MODULE_BASE + 0x1E                    # non-zero while a tune plays
SFX_ACTIVE = MODULE_BASE + 0x1F                      # non-zero while an effect runs
MASTER_VOLUME = MODULE_BASE + 0x25                   # ships 0x0f = no attenuation; never written
MASTER_VOLUME_SHIPPED = 0x0F

# The driver's whole mutable state, and therefore the loop detector's subject: the variable block
# (PSG shadow, sfx generator, sequencer flags and counters) followed by the three channel structs.
# Nothing else in the image is written by a tick, so two equal states produce equal futures.
STATE_LO = MODULE_BASE + 0x00
STATE_HI = MODULE_BASE + 0x26
CHANNEL_STRUCTS_LO = MODULE_BASE + 0x568             # 0x58eac, and the end of the tune table below
CHANNEL_STRIDE = 24
CHANNEL_STRUCTS_HI = CHANNEL_STRUCTS_LO + CHANNEL_STRIDE * ym_capture.CHANNELS

# How many tunes and how many effects there are is each TABLE'S OWN LENGTH, not a number typed here:
# a count too small dumps a subset in silence, and one too large runs `music_start` off the end of
# its table into whatever follows. Both spans are bounded by a neighbour this tool already knows —
# the tune table runs up to the first channel struct, and the effect table ends the module's TEXT
# (notes/sound_engine.md, "the sound-effect format") — and `check_staging_matches_the_game` pins the
# second against the length in MODULE.BAK's own header.
TUNE_TABLE = MODULE_BASE + 0x540                     # 0x58e84: music_start reads tune_table + n*8
TUNE_RECORD_BYTES = 8
SFX_TABLE = MODULE_BASE + 0xF5E                      # 0x598a2: sfx_start reads sfx_table + n*18
SFX_RECORD_BYTES = 18
MODULE_TEXT_BYTES = 0x1048                           # MODULE.BAK's header says so; pinned, not read

TUNE_COUNT = (CHANNEL_STRUCTS_LO - TUNE_TABLE) // TUNE_RECORD_BYTES
SFX_COUNT = (MODULE_BASE + MODULE_TEXT_BYTES - SFX_TABLE) // SFX_RECORD_BYTES

# ---- the pins against the reconstruction's own header ----------------------------------------------
# `../recreate/include/globals.h` states three of the addresses above for the port, and this tool
# derives its own from the game (the file-table record, and `dest + the .PRG header`). Two readings
# of one program, so they have to agree — and a `#define` that has gone counts as a disagreement
# rather than as a satisfied pin, because the alternative is a number typed in two files drifting
# apart in silence. Everything else here is the MODULE's, which the header does not describe.
#
# The scraper is a scraper and not an import: `globals.h` is a header, and reading it is how the
# sibling extractors (projects/bubbleghost/tools/extract_audio.py) pin the same class of constant.
# A value built from other macros is deliberately out of reach — evaluating one would be a C
# preprocessor — so every name below is a plain literal over there.
DEFINE_RE = re.compile(r"^#define\s+(?P<name>\w+)\s+(?P<value>0[xX][0-9a-fA-F]+|\d+)[uU]?"
                       r"(?=\s*(?:/[/*]|$))", re.M)
GLOBALS_H = os.path.join(RECREATE_DIR, "include", "globals.h")

# (this tool's name for it, its value, the `globals.h` define that has to agree).
GLOBALS_H_PINS = (
    ("MODULE_BASE", MODULE_BASE, "A_sound_module"),
    ("MODULE_HEADER_BYTES", MODULE_HEADER_BYTES, "SOUND_MODULE_HEADER_BYTES"),
    ("MODULE_TABLE_ENTRY", MODULE_TABLE_ENTRY, "A_file_rec_module_bak"),
)


def header_defines(path):
    """{name: value} for every plain-integer `#define` in one C header."""
    with open(path) as handle:
        return {found["name"]: int(found["value"], 0) for found in DEFINE_RE.finditer(handle.read())}


def check_layout_matches_the_reconstruction():
    """Where this tool thinks the sound module lives is where `../recreate/include/globals.h` does.

    Everything is reported at once rather than first-match: these three move together, and a message
    naming one sends the reader back for the next.
    """
    defines = header_defines(GLOBALS_H)
    wrong = ["%s is %#x here, %s is %s there"
             % (name, mine, define, "absent" if defines.get(define) is None
                else "%#x" % defines[define])
             for name, mine, define in GLOBALS_H_PINS if mine != defines.get(define)]
    if wrong:
        raise SystemExit("this tool and %s disagree about where the sound module lives: %s. One of "
                         "the two readings of the original is wrong, and a capture staged on the "
                         "wrong address is a plausible dump of the wrong bytes"
                         % (os.path.relpath(GLOBALS_H, PROJECT_DIR), "; ".join(wrong)))


# ---- the chip, and how a tick reaches it -----------------------------------------------------------
# The register numbers and the audibility rule are the CHIP's and live in tools/ym_capture.py; only
# what is specific to THIS driver is named here.

FRAME_RATE = 50                                      # the VBL, which is what a tick is

# Every tick ends by pushing the 13-byte shadow out in this order (sound_engine.md, "the tick",
# step 6). The ORDER is checked and not just the count, because a driver that flushed the same
# registers the other way round leaves an identical register file behind and only the ledger can see
# the difference — a coarse period landing before its fine byte is a real, audible bug class.
TICK_FLUSH_ORDER = (1, 0, 3, 2, 5, 4, 6, 7, 8, 9, 10, 12, 11)
ENVELOPE_SHAPE_REG = 13                              # appended on the ticks that latch a shape

# Which bits of each register the CHIP decodes. It matters for the .ym and not for the render:
# YM5/YM6 reuse the dead bits of registers 1, 3, 6, 7, 14 and 15 as SPECIAL-EFFECT CODES, so a
# player handed a raw shadow byte with rubbish above the field starts an effect on whatever voice
# those bits happen to name.
TONE_PERIOD_COARSE_MASK = 0x0F
NOISE_PERIOD_MASK = 0x1F
MIXER_MASK = 0x3F                                    # 3 tone gates + 3 noise gates
VOLUME_REG_MASK = 0x1F                               # 4-bit level + the envelope-mode bit
ENVELOPE_SHAPE_MASK = 0x0F
YM_REGISTER_MASKS = bytes((
    0xFF, TONE_PERIOD_COARSE_MASK,                   # 0/1: channel A tone period
    0xFF, TONE_PERIOD_COARSE_MASK,                   # 2/3: channel B
    0xFF, TONE_PERIOD_COARSE_MASK,                   # 4/5: channel C
    NOISE_PERIOD_MASK,                               # 6:   noise period
    MIXER_MASK,                                      # 7:   mixer
    VOLUME_REG_MASK, VOLUME_REG_MASK, VOLUME_REG_MASK,   # 8-10: channel volumes
    0xFF, 0xFF,                                      # 11/12: envelope period
    ENVELOPE_SHAPE_MASK,                             # 13:   envelope shape
    0xFF, 0xFF,                                      # 14/15: the I/O ports, never written
))

# Register 13 is WRITE-TRIGGERED on the real chip — writing it restarts the envelope generator —
# so the YM formats spell "not written this frame" as 0xff rather than as a repeat of the shape.
ENVELOPE_SHAPE_UNTOUCHED = 0xFF

# What `check_sfx_preempts_channel_c` compares, and it is deliberately not the whole register file.
# Registers 0..3 and 8..9 are channels A and B's periods and volumes; register 6 is the noise period
# ALL THREE CHANNELS SHARE, which the tick's effect branch does write (`move.b sfx_period_current+1,
# 6(a3)` at 0x58a54, on the ticks its noise pattern selects) and which is therefore the one place an
# effect could reach A or B without touching a register of theirs; register 7's four A/B gate bits
# are the third. The rest are excluded with a reason: 4, 5 and 10 are channel C, i.e. the
# pre-emption itself; 11, 12 and 13 are the ENVELOPE GENERATOR, which an effect does move and which
# is inaudible on A and B for as long as neither selects it — pinned in the same check, not assumed;
# 14 and 15 are the I/O ports and are never written.
CHANNEL_AB_REGS = (0, 1, 2, 3, 8, 9)
NOISE_PERIOD_REG = 6
MIXER_AB_GATE_MASK = 0x1B                            # bits 0,1 = A/B tone; bits 3,4 = A/B noise

if len(YM_REGISTER_MASKS) != ym_capture.YM_REGISTERS or emu.PSG_NREGS != ym_capture.YM_REGISTERS:
    sys.exit("the chip is %d registers wide here, %d in tools/ym_capture.py and %d in liboracle.so; "
             "the mask table and the shadow have to be the same file the .ym writer expects"
             % (len(YM_REGISTER_MASKS), ym_capture.YM_REGISTERS, emu.PSG_NREGS))

if ((CHANNEL_STRUCTS_LO - TUNE_TABLE) % TUNE_RECORD_BYTES
        or (MODULE_BASE + MODULE_TEXT_BYTES - SFX_TABLE) % SFX_RECORD_BYTES):
    sys.exit("the tune table spans %d bytes of %d-byte records and the effect table %d of %d: a "
             "span that is not a whole number of records means one of the four addresses above is "
             "wrong, and the counts derived from them would sweep past the end of a table"
             % (CHANNEL_STRUCTS_LO - TUNE_TABLE, TUNE_RECORD_BYTES,
                MODULE_BASE + MODULE_TEXT_BYTES - SFX_TABLE, SFX_RECORD_BYTES))

YM6_AUTHOR = "Flying Shark (Firebird 1988), A\\MODULE.BAK"

# ---- the sweep -------------------------------------------------------------------------------------

TUNE_FRAME_CAP = 3 * 60 * FRAME_RATE                 # 3 minutes: nothing in this set approaches it
SFX_FRAME_CAP = 10 * FRAME_RATE                      # 10 s: the longest effect is 80 frames

END_ENDED = "ended"                                  # the driver cleared its own active flag
END_LOOP = "loop"                                    # its whole state repeated
END_CAPPED = "capped"                                # neither, inside the cap

KIND_MUSIC = "music"
KIND_SFX = "sfx"
KIND_MIX = "mix"

# What ends a capture of each kind: the driver's own active flag, and the cap that stops it if the
# flag never clears. The combined example is a TUNE with an effect injected into it, so it ends the
# way a tune does — `sfx_active` clearing six frames in would cut the music off mid-phrase.
CAPTURE_LIMITS = {
    KIND_MUSIC: (MUSIC_ACTIVE, TUNE_FRAME_CAP),
    KIND_SFX: (SFX_ACTIVE, SFX_FRAME_CAP),
    KIND_MIX: (MUSIC_ACTIVE, TUNE_FRAME_CAP),
}

# The combined example. Effect 5 is the one the game starts most (ten call sites through the
# 0x121ce wrapper, plus the inline site at 0x1293a), and tune 1 is the level-1 theme; frame 100 is
# two seconds in, well past the tune's opening.
MIX_TUNE = 1
MIX_SFX = 5
MIX_INJECT_FRAME = 100

# The two tracks `check_capture_is_reproducible` captures twice. A LOOPING tune is the one worth
# re-running, because the loop detector's state dictionary is the only thing in a capture that
# accumulates across frames, and tune 2 is the cheapest of the three that loop; effect 10 is the
# longest effect. The whole sweep is not re-run: what this catches — a run reading something the
# staged image does not carry — is shared by every track, and doubling the capture to say it
# nineteen times over says nothing the first two do not.
REPRO_TUNE = 2
REPRO_SFX = 10

# What the GAME does with each number, from notes/sound_engine.md, "Which game event plays what".
# This is a reading of the call sites carried here as text: no check backs it, and the manifest says
# so. The per-level mapping is level_table[+4], read at 0x125b0: L1->1, L2->3, L3->2, L4->1, L5->2.
TUNE_EVENTS = {
    0: "boss theme; music_start(0) at 0x124f8 when the level progress counter passes level_table[+0]",
    1: "level theme for stages 1 and 4; music_start at 0x125b0 via level_table[+4]",
    2: "level theme for stages 3 and 5; music_start at 0x125b0 via level_table[+4]",
    3: "level theme for stage 2; music_start at 0x125b0 via level_table[+4]",
    4: "level-start jingle; music_start(4) at 0x1054e, and 0x1054a waits on music_active",
}
SFX_EVENTS = {
    2: "wrapper at 0x121e6, 5 call sites",
    5: "wrapper at 0x121ce, 10 call sites; also inline at 0x1293a behind a tst.b sfx_active guard",
    6: "wrapper at 0x1217a (sfx_play_6)",
    10: "wrapper at 0x121b6; called from 0x10c98 and 0x11014, tail-jumped from 0x12176",
    11: "inline at 0x13e32, behind a tst.b sfx_active guard",
    12: "NOT REACHABLE in the shipped game: no call site starts it, and clear_actor_arrays (0x115e2)"
        " zeroes the last 8 bytes of its record — the entity arena at 0x59984 overlaps the module's"
        " last 9 staged bytes. Captured from the pristine file, which is what the file holds",
}
NO_KNOWN_EVENT = "-"                                 # reachable, but no call site named in the notes

# `frames[i]` is the register file tick i+1 flushed; `retriggers[i]` says tick i+1 wrote register 13.
# `loop_start` is the frame index the loop returns to, and `loop_period` its length in frames.
# `inject` is carried so that a re-capture reproduces the same capture and not a different one.
# `loop_image` / `loop_shadow` are the machine the capture STOPPED in — which, a loop having been
# proved, is the machine frame `loop_start` was produced from — so `check_loop_replays` resumes
# there instead of driving the whole track a second time. All four loop fields are None otherwise.
Capture = namedtuple("Capture",
                     "kind number name inject frames retriggers end "
                     "loop_start loop_period loop_image loop_shadow",
                     defaults=(None, None, None, None))
Track = namedtuple("Track", "capture audible peak")
# What `check_sfx_preempts_channel_c` measured: the frames on which channel C was in envelope mode
# under the effect and not under the music alone, and how many frames the two captures were
# compared over — the report states both rather than rounding them into "the whole capture".
Preemption = namedtuple("Preemption", "envelope_frames compared_frames")


# ---- staging the image -----------------------------------------------------------------------------


def module_staging(image):
    """(destination, length) for A\\MODULE.BAK, read out of the GAME's own relocated file table.

    Refuses rather than falls back if the record does not name the module: an entry that has moved
    means this address is stale, and staging the driver somewhere else would produce a dump of
    whatever bytes happened to be there — silently, since the module is position-independent and
    would still be entered.
    """
    name_at = MODULE_TABLE_ENTRY + TABLE_NAME
    name = bytes(image[name_at:name_at + len(MODULE_TABLE_NAME)])
    if name != MODULE_TABLE_NAME:
        raise SystemExit("FLYSHARK.PRG's file-table record at %#x names %r, not %r — out/prg_dis.txt "
                         "has moved on and this address no longer points at the sound module"
                         % (MODULE_TABLE_ENTRY, name, MODULE_TABLE_NAME))
    dest = struct.unpack_from(TABLE_LONG, image, MODULE_TABLE_ENTRY + TABLE_DEST)[0]
    length = struct.unpack_from(TABLE_LONG, image, MODULE_TABLE_ENTRY + TABLE_LENGTH)[0]
    return dest, length


def check_module_is_position_independent(module):
    """The module may be dropped at an address of the game's choosing — say so from its own header.

    ABSFLAG set with no relocation table is what makes `MODULE_BASE` a matter of where the game
    points `a0` rather than of a load-time fixup. If that ever stopped being true, placing the bytes
    raw would leave every absolute reference inside them pointing at 0.
    """
    header = loader.prg_dis.parse_header(module)     # the kit's own .PRG header parse, not a second
    if (header["magic"] != PRG_MAGIC or header["absf"] != PRG_ABSFLAG_NO_RELOC
            or header["dlen"] or header["blen"]):
        raise SystemExit("MODULE.BAK is not the header notes/sound_engine.md describes: magic %#06x "
                         "absflag %#06x text %d data %d bss %d — expected %#06x / %#06x and text "
                         "only. It can no longer be placed raw."
                         % (header["magic"], header["absf"], header["tlen"], header["dlen"],
                            header["blen"], PRG_MAGIC, PRG_ABSFLAG_NO_RELOC))
    return header["tlen"]


def check_staging_matches_the_game(dest, length, module, text_bytes):
    """The staging this tool performs is the staging the game performs.

    Five separate ways of being wrong, and none of them is audible in the result: the module at a
    different address (every `a0`-relative reference would still work, on the wrong bytes); the
    entry points at an offset from a base the game does not use; a length that truncates the effect
    table; a TEXT that no longer ends where `SFX_COUNT` counts effects up to; a module whose data
    has been edited under the tool.
    """
    if dest + MODULE_HEADER_BYTES != MODULE_BASE:
        raise SystemExit("the game reads MODULE.BAK to %#x and calls it at %#x (dest + %d), but this "
                         "tool's entry points are at %#x + their offsets"
                         % (dest, dest + MODULE_HEADER_BYTES, MODULE_HEADER_BYTES, MODULE_BASE))
    if length > len(module):
        raise SystemExit("the file table asks for %d bytes of MODULE.BAK and the file holds %d"
                         % (length, len(module)))
    if length < MODULE_HEADER_BYTES + text_bytes:
        raise SystemExit("the file table reads %d bytes of MODULE.BAK, short of its %d-byte header "
                         "plus %d bytes of text — the effect table at the end of TEXT would be cut"
                         % (length, MODULE_HEADER_BYTES, text_bytes))
    if text_bytes != MODULE_TEXT_BYTES:
        raise SystemExit("MODULE.BAK's header says %d bytes of TEXT, not the %d this tool counts "
                         "%d effects of %d bytes up to — the effect table ends the module, so a "
                         "different TEXT length is a different number of effects"
                         % (text_bytes, MODULE_TEXT_BYTES, SFX_COUNT, SFX_RECORD_BYTES))
    shipped = module[MODULE_HEADER_BYTES + MASTER_VOLUME - MODULE_BASE]
    if shipped != MASTER_VOLUME_SHIPPED:
        raise SystemExit("MODULE.BAK ships master_volume = %#04x, not %#04x. The module has no init "
                         "entry, so that byte is the one thing a capture inherits from the file, and "
                         "a smaller value clips the quiet envelope steps to silence"
                         % (shipped, MASTER_VOLUME_SHIPPED))


def staged_image():
    """The game's image with the sound module read into it exactly as the game reads it."""
    image = loader.load_image(GAME_PRG)
    with open(MODULE_FILE, "rb") as handle:
        module = handle.read()
    text_bytes = check_module_is_position_independent(module)
    dest, length = module_staging(image)
    check_staging_matches_the_game(dest, length, module, text_bytes)
    image[dest:dest + length] = module[:length]
    return image


SHIFTER_SYNC = 0xFF820A                              # the shifter's sync-mode byte
SHIFTER_SYNC_50HZ = 1 << 1                           # bit 1 set = 50 Hz (clear = 60 Hz)


def check_tempo_profile():
    """The audio-capture mode really is declaring a 50 Hz machine on `$ff820a`. Returns the byte.

    Bit 1 set = 50 Hz, so the tick runs every frame; clear = 60 Hz, and the driver drops one tick in
    six to hold the sequencer at 50 steps per second. An unseeded read is served 0 — the 60 Hz
    machine — and every track would come out a fifth too slow with nothing in the .ym to say so.
    """
    profile = emu.hw_capture_profile()
    sync = profile.get(SHIFTER_SYNC)
    if sync is None or not sync & SHIFTER_SYNC_50HZ:
        raise SystemExit("the audio-capture mode serves $ff820a = %s, whose bit 1 (50 Hz) is clear. "
                         "sound_vbl_tick would take the 60 Hz path and drop one tick in six"
                         % ("nothing" if sync is None else "%#04x" % sync))
    return sync


# ---- driving the driver ----------------------------------------------------------------------------


def run(image, entry, regs=None):
    """One oracle run. Returns (final image, its `(reg, value)` PSG writes).

    `emu.run` raises on anything it cannot model, and that is left to propagate: mid-capture it
    means the driver reached a hardware access notes/sound_engine.md does not describe, which is a
    finding rather than something to work around.
    """
    image, _writes, _regs = emu.run(image, entry, regs)
    return image, vetted_psg_writes()


def vetted_psg_writes():
    """The last run's writes, with the one assumption this tool rests on checked.

    A chip READ would mean the capture was served an answer the audio-capture mode invented rather
    than one the game's data produced (TRAP_MODEL.md, Phase 6). The driver keeps its own shadow at
    `MODULE_BASE` and pushes it blind, so there should never be one — and if there were, the dump
    would rest on `shim.c` and nothing in the .wav would say so.
    """
    events = emu.psg_events()
    for kind, reg, value in events:
        if kind != os_map.OS_PSG_EVENT_WRITE:
            raise SystemExit("the driver READ PSG register %d (served %#x). It keeps its own shadow "
                             "at %#x and pushes it blind, so this answer is the audio-capture mode's "
                             "invention and the dump would rest on it" % (reg, value, MODULE_BASE))
    return [(reg, value) for _kind, reg, value in events]


def tick(image, name, frame):
    """One 50 Hz frame. Returns (image, the writes it made, whether it latched an envelope shape)."""
    image, writes = run(image, SOUND_VBL_TICK, {"a0": MODULE_BASE})
    pushed = tuple(reg for reg, _value in writes)
    if pushed not in (TICK_FLUSH_ORDER, TICK_FLUSH_ORDER + (ENVELOPE_SHAPE_REG,)):
        raise SystemExit("%s tick %d pushed registers %s, not the %s notes/sound_engine.md says "
                         "every tick flushes (optionally followed by register %d)"
                         % (name, frame, list(pushed), list(TICK_FLUSH_ORDER), ENVELOPE_SHAPE_REG))
    return image, writes, len(pushed) > len(TICK_FLUSH_ORDER)


def ym_frame(shadow):
    """One frame's register file, masked to the bits the chip decodes."""
    return bytes(byte & mask for byte, mask in zip(shadow, YM_REGISTER_MASKS))


def driver_state(image):
    """The driver's mutable bytes: everything the next tick reads, and nothing else."""
    return (bytes(image[STATE_LO:STATE_HI])
            + bytes(image[CHANNEL_STRUCTS_LO:CHANNEL_STRUCTS_HI]))


def start_track(kind, number):
    """A freshly staged image with `number` armed, and the empty register shadow that goes with it."""
    image = staged_image()
    entry = SFX_START if kind == KIND_SFX else MUSIC_START
    image, _writes = run(image, entry, {"d0": number, "a0": MODULE_BASE})
    return image, bytearray(ym_capture.YM_REGISTERS)


def drive(image, shadow, name, inject=None, first_frame=0):
    """Tick the driver for ever, yielding `(image, that frame's register file, latched)` each frame.

    The capture and its loop replay both run through this one loop: they differ in where they start
    and in what stops them, and nowhere else. A second copy of the injection and the fold is a
    second place for either to drift from the capture it is supposed to be checking.

    `first_frame` is the index this run's first frame carries — the capture's own numbering, so a
    replay that resumes at the loop point reports the frame numbers of the track it is checking.
    """
    frame = first_frame
    while True:
        if inject is not None and frame == inject[0]:
            image, _writes = run(image, SFX_START, {"d0": inject[1], "a0": MODULE_BASE})
        image, writes, latched = tick(image, name, frame + 1)
        ym_capture.fold(shadow, writes)
        yield image, ym_frame(shadow), latched
        frame += 1


def capture(kind, number, name, inject=None):
    """Drive the driver from a freshly staged image and return one track's per-frame register files.

    `inject` is `(frame index, effect number)`: `sfx_start` is called just before that frame's tick,
    which is how the game itself starts an effect over a running tune (its VBL handler is the only
    tick site, and every wrapper is called from the game loop between two of them).

    `state_seen[state]` is the frame index the state was FIRST reached at, with the register shadow
    as it stood just before that frame. Frame i is the flush of tick i+1 and `state` is that same
    tick's state, so a repeat at frame i of the state first seen at frame j means frames j..i-1 are
    the loop: the capture keeps them and stops. The shadow is kept alongside because register 13 is
    the one byte a tick does not always rewrite, so a replay resuming from the repeated state has to
    inherit the shape the first pass held there rather than the one this pass ends on.
    """
    active_flag, frame_cap = CAPTURE_LIMITS[kind]
    image, shadow = start_track(kind, number)
    frames, retriggers, state_seen = [], [], {}
    for image, registers, latched in drive(image, shadow, name, inject):
        frames.append(registers)
        retriggers.append(latched)
        if not image[active_flag]:
            return Capture(kind, number, name, inject, frames, retriggers, END_ENDED)
        state = driver_state(image)
        if state in state_seen:
            start, loop_shadow = state_seen[state]
            return Capture(kind, number, name, inject, frames, retriggers, END_LOOP,
                           start, len(frames) - start, image, loop_shadow)
        state_seen[state] = (len(frames), bytes(shadow))
        if len(frames) == frame_cap:
            return Capture(kind, number, name, inject, frames, retriggers, END_CAPPED)


def check_loop_replays(result):
    """Play a proven loop's next period out and compare it, frame by frame, with the first.

    The loop argument is that equal state implies equal future; this is the argument being run
    rather than asserted, and it is the one surface that would catch a `driver_state` span that had
    stopped covering everything a tick reads — which is exactly how a "loop" that is really a near
    miss gets into a dump, audible only as a track that jumps a note on repeat.

    The replay RESUMES from the state the capture stopped in, which is the whole point of the claim
    being checked: that state is the one frame `loop_start` was produced from, so the next period is
    one period of ticks rather than a whole second capture plus one. `inject` is carried anyway,
    even though a capture that looped after its injection can never reach that frame index again:
    one that looped BEFORE it has to have the effect arrive on the frame it was asked for, and then
    diverge honestly, rather than replay a period the game would never have played.
    """
    if result.end != END_LOOP:
        return
    replay = drive(result.loop_image, bytearray(result.loop_shadow), result.name,
                   inject=result.inject, first_frame=len(result.frames))
    for offset, (_image, registers, _latched) in zip(range(result.loop_period), replay):
        expected = result.frames[result.loop_start + offset]
        if registers != expected:
            raise SystemExit("%s claims a %d-frame loop from frame %d, but replaying it diverges %d "
                             "frames in — the state span the detector watches is not everything a "
                             "tick reads" % (result.name, result.loop_period, result.loop_start,
                                             offset))


def check_capture_is_reproducible(tunes, effects):
    """A track captured a second time comes out the same: same frames, same end, same loop.

    Every other check here reads ONE capture, so a run that depended on something the staged image
    does not carry — a register the oracle left set, a shadow leaked from the track before, a
    dictionary keyed on identity rather than value — would satisfy all of them and still hand the
    next run a different dump. This is the only check that would notice, and it is the reason the
    files in the directory can be called the game's data rather than one run's.
    """
    for original in (tunes[REPRO_TUNE], effects[REPRO_SFX]):
        again = capture(original.kind, original.number, original.name, original.inject)
        if (again.frames == original.frames and again.end == original.end
                and again.loop_start == original.loop_start
                and again.loop_period == original.loop_period):
            continue
        differs = next((frame for frame in range(min(len(again.frames), len(original.frames)))
                        if again.frames[frame] != original.frames[frame]), None)
        raise SystemExit("%s captured twice came out differently: %d frames, %s the first time and "
                         "%d frames, %s the second%s. A capture that does not repeat is a reading "
                         "of the run and not of the game's data"
                         % (original.name, len(original.frames), end_description(original),
                            len(again.frames), end_description(again),
                            "" if differs is None else "; first differing frame is %d" % differs))


# ---- audibility, and the render --------------------------------------------------------------------


def track_audible_frames(result):
    """How many of a capture's frames would make a sound, under THIS driver's envelope rule.

    `ym_capture.channel_sounds` reads a channel whose volume register selects the ENVELOPE generator
    (bit 4) as silent by default, because the drivers it was written for never trigger one. Every
    Flying Shark sound effect drives channel C exactly that way — volume 0x10 with shape 0x09 latched
    into register 13 (notes/sound_engine.md, "the sound-effect format") — so the default rule reports
    all 13 effects as pure silence, and `envelope_is_level` is the policy that says otherwise here:
    an envelope-mode channel with a gate open is sounding, the generator being what is running, and
    every effect's own duration counter ends it long before a single 0x09 ramp has decayed away.
    """
    return ym_capture.audible_frames(result.frames, envelope_is_level=True)


def check_every_track_is_audible(audible):
    """Every track must make a sound on the chip in at least one of its frames.

    Without it a sweep that captured 19 silent tracks would pass everything else here: the flush
    order, the loop replays, the pre-emption example and the silence check all hold of a set of
    empty tracks, and the one thing that would be wrong — an entry point or a table offset off by a
    record, so that every `music_start` armed nothing — is invisible in a .ym full of zeroes. The
    bar is one frame rather than a proportion, because a 4-frame blip and a 107-second theme are
    both in this set and any threshold above 1 would be a claim about the music, not the capture.
    """
    silent = sorted(name for name, frames in audible.items() if not frames)
    if silent:
        raise SystemExit("%d of %d tracks are silent on the chip across every one of their frames "
                         "(%s): no gate open over a level or a running envelope anywhere. A sweep "
                         "that records the driver muted is a truthful dump of nothing"
                         % (len(silent), len(audible), ", ".join(silent)))


def render(result):
    """One capture's float track, on the chip's own scale.

    `normalise=False` keeps two renders comparable — an effect that is genuinely quiet stays quiet
    instead of being amplified into the loudest file in the set. `retriggers` is what makes the
    envelope right: a register-13 write restarts the generator on real hardware, and every effect
    depends on that restart for its attack.
    """
    return ym2149.render(result.frames, retriggers=result.retriggers, normalise=False)


def ym_frames(result):
    """The capture's frames with register 13's "not written this frame" convention honoured.

    The shadow carries the latched shape forward, which is what the chip does and what the RENDER
    needs; a .ym file instead spells an untouched register 13 as 0xff, so that a player retriggers
    the envelope on exactly the frames the driver did.
    """
    out = []
    for frame, latched in zip(result.frames, result.retriggers):
        if latched:
            out.append(frame)
            continue
        frame = bytearray(frame)
        frame[ENVELOPE_SHAPE_REG] = ENVELOPE_SHAPE_UNTOUCHED
        out.append(bytes(frame))
    return out


def write_assets(out_dir, result):
    """One track's .ym and .wav. Returns the render's peak, 0..1."""
    stem = os.path.join(out_dir, result.name)
    comment = "%d frames at %d Hz, %s" % (len(result.frames), FRAME_RATE, end_description(result))
    ym_capture.write_ym6(stem + ".ym", ym_frames(result), result.name, YM6_AUTHOR, comment,
                         FRAME_RATE, ym2149.CLOCK, result.loop_start or 0)
    return ym_capture.write_wav(stem + ".wav", render(result), ym2149.RATE)


def check_silence_agrees_with_the_render(tracks):
    """A track the register stream calls audible must render above silence, and the reverse.

    Two independent readings of the same frames — `channel_sounds` on the register file, and the
    synth's own output — and a disagreement means one of them is wrong about the chip. It is the
    check that would catch `channel_sounds`'s envelope extension being too generous (a track counted
    audible that renders as nothing) or too mean.
    """
    for track in tracks:
        rendered = track.peak > ym_capture.RENDER_SILENCE_PEAK
        if bool(track.audible) != rendered:
            raise SystemExit("%s has %d audible frames by its register stream but renders at a peak "
                             "of %g: the two readings of the same frames disagree"
                             % (track.capture.name, track.audible, track.peak))


def check_sfx_preempts_channel_c(tune, mix):
    """The combined example really does show an effect taking channel C and only channel C.

    notes/sound_engine.md, "the tick" step 5, claims an effect "overwrites whatever the music just
    put on channel C — effects pre-empt the music there and nowhere else". Three things are asked of
    the combined capture, and the sentence only has two:

      * everything channels A and B are made of is identical to the tune played alone for the whole
        capture — their periods and volumes, the four mixer bits that gate them, and the NOISE
        PERIOD they share with C, which the effect branch does write and which is the one register
        through which an effect could reach a channel that is not its own;
      * neither A nor B ever hands itself to the envelope generator, which is what makes registers
        11..13 — the generator's own, and the effect DOES move them — inaudible on those two
        channels rather than merely unexamined;
      * channel C's volume goes into envelope mode on frames after the injection, which it never
        does under the music alone.
    """
    span = min(len(tune.frames), len(mix.frames))
    gates = ym_capture.PSG_MIXER_REG
    for frame in range(span):
        for reg in CHANNEL_AB_REGS + (NOISE_PERIOD_REG,):
            if tune.frames[frame][reg] != mix.frames[frame][reg]:
                raise SystemExit("effect %d disturbed PSG register %d at frame %d of tune %d: an "
                                 "effect is supposed to own channel C, and %s"
                                 % (MIX_SFX, reg, frame, MIX_TUNE,
                                    "the noise period is shared with A and B"
                                    if reg == NOISE_PERIOD_REG else "that register is A's or B's"))
        if (tune.frames[frame][gates] ^ mix.frames[frame][gates]) & MIXER_AB_GATE_MASK:
            raise SystemExit("effect %d moved a channel A or B gate bit (mixer %#04x -> %#04x, mask "
                             "%#04x) at frame %d of tune %d: an effect owns channel C's gates only"
                             % (MIX_SFX, tune.frames[frame][gates], mix.frames[frame][gates],
                                MIXER_AB_GATE_MASK, frame, MIX_TUNE))
        for channel in range(ym_capture.CHANNELS - 1):
            volume = mix.frames[frame][ym_capture.PSG_VOLUME_A_REG + channel]
            if volume & ym_capture.VOLUME_ENVELOPE_BIT:
                raise SystemExit("channel %s took the envelope generator (volume %#04x) at frame %d "
                                 "of tune %d: registers 11..13 are then audible on it, and this "
                                 "check does not compare them"
                                 % ("ABC"[channel], volume, frame, MIX_TUNE))
    volume_c = ym_capture.PSG_VOLUME_A_REG + ym_capture.CHANNELS - 1
    preempted = [frame for frame in range(MIX_INJECT_FRAME, span)
                 if mix.frames[frame][volume_c] & ym_capture.VOLUME_ENVELOPE_BIT
                 and not tune.frames[frame][volume_c] & ym_capture.VOLUME_ENVELOPE_BIT]
    if not preempted:
        raise SystemExit("effect %d injected at frame %d never put channel C into hardware-envelope "
                         "mode, so the combined capture shows no pre-emption at all"
                         % (MIX_SFX, MIX_INJECT_FRAME))
    return Preemption(preempted, span)


# ---- the manifest ----------------------------------------------------------------------------------

MANIFEST_COLUMNS = ("kind", "number", "file", "frames", "seconds", "ended", "loop_start",
                    "loop_frames", "audible_frames", "peak_dbfs", "game_event")

MANIFEST_HEADER = """\
# Flying Shark (ST) — every tune and sound effect in the game's sound driver, captured from
# bin/FLYSHARK.PRG + bin/disk/A/MODULE.BAK by projects/flyingshark/tools/extract_audio.py by running
# the ORIGINAL 68000 driver under the recreate kit's Musashi oracle. One row per track; the .ym and
# .wav named in the `file` column sit beside this file. See notes/sound_engine.md.
#
# kind      music = one of the 5 tunes (music_start, d0.b = 0..4)
#           sfx   = one of the 13 effects (sfx_start, d0.b = 0..12), captured on a SILENT chip
#           mix   = the one combined example: tune %d with effect %d started at frame %d
# frames    one 50 Hz VBL tick each: the driver was entered at sound_vbl_tick once per frame with
#           $ff820a = %#04x (bit 1 set = a 50 Hz machine, so no tick is dropped).
# ended     ended  = the driver cleared its own active flag (pattern command 0x88 for a tune; the
#                    duration counter running out for an effect)
#           loop   = its whole mutable state returned to a value it had held, so the output repeats
#                    for ever. The file holds the lead-in plus exactly one period, and the next
#                    period was replayed and compared frame by frame before this file was written.
#           capped = neither, inside %d frames for a tune / %d for an effect
# loop_start the frame the loop returns to, which is also the .ym's loop field. "-" if it does not
#           loop; a looping .ym is meant to be played on repeat.
# audible_frames  frames that would make a sound on the chip. A channel in HARDWARE-ENVELOPE mode
#           counts as sounding, which is how every effect drives channel C — under the DEFAULT of
#           the shared tools/ym_capture.py rule all 13 read as silent.
# peak_dbfs the .wav's peak on the CHIP's scale (0 dBFS = three channels at volume 15), so the
#           numbers are comparable between files rather than each normalised to itself.
# game_event  which call site in FLYSHARK.PRG starts this number, from notes/sound_engine.md,
#           "Which game event plays what". THIS COLUMN IS A READING, not a measurement: no check in
#           the tool backs it, and "-" means no call site was named for that number — not that the
#           number is unreachable. sfx 12 is the one entry that says the opposite, and the .ym is
#           still the file's own content.
"""


def end_description(result):
    """The `ended` column, and the .ym comment: how the capture stopped, with its loop if it has one."""
    if result.end != END_LOOP:
        return result.end
    return "%s of %d frames from frame %d" % (END_LOOP, result.loop_period, result.loop_start)


def game_event(result):
    """The `game_event` column: what the notes say starts this number."""
    if result.kind == KIND_MIX:
        return "not a game event: this tool's combined example"
    events = TUNE_EVENTS if result.kind == KIND_MUSIC else SFX_EVENTS
    return events.get(result.number, NO_KNOWN_EVENT)


def manifest_row(track):
    result = track.capture
    return "\t".join((
        result.kind,
        "%d+%d" % (MIX_TUNE, MIX_SFX) if result.kind == KIND_MIX else str(result.number),
        result.name,
        str(len(result.frames)),
        "%.2f" % (len(result.frames) / FRAME_RATE),
        result.end,
        str(result.loop_start) if result.loop_start is not None else "-",
        str(result.loop_period) if result.loop_period is not None else "-",
        str(track.audible),
        ym_capture.peak_dbfs(track.peak),
        game_event(result),
    ))


# ---- the run -----------------------------------------------------------------------------------------


def end_tally(tracks):
    counts = {end: sum(1 for track in tracks if track.capture.end == end) for end in
              (END_ENDED, END_LOOP, END_CAPPED)}
    return ", ".join("%d %s" % (count, end) for end, count in counts.items() if count)


def report(tracks, sync, preemption, out_dir):
    total = sum(len(track.capture.frames) for track in tracks)
    longest = max(tracks, key=lambda track: len(track.capture.frames)).capture
    loudest = max(tracks, key=lambda track: track.peak)
    return "\n".join((
        "tracks: %d captured — %d tunes, %d effects, 1 combined example"
        % (len(tracks), TUNE_COUNT, SFX_COUNT),
        "ends:   %s (caps: %d frames for a tune, %d for an effect)"
        % (end_tally(tracks), TUNE_FRAME_CAP, SFX_FRAME_CAP),
        "length: %d frames = %.1f s at %d Hz; longest is %s at %.1f s"
        % (total, total / FRAME_RATE, FRAME_RATE, longest.name, len(longest.frames) / FRAME_RATE),
        "tempo:  $ff820a served %#04x by the audio-capture profile — bit 1 set, so the 50 Hz path "
        "runs every tick and nothing is dropped" % sync,
        "levels: rendered on the chip's scale (0 dBFS = 3 channels at volume 15), so no file clips "
        "and the levels are comparable; loudest is %s at %s dBFS"
        % (loudest.capture.name, ym_capture.peak_dbfs(loudest.peak)),
        "mix:    effect %d over tune %d holds channel C in envelope mode for frames %d..%d; over "
        "all %d frames compared, PSG %s (A and B's periods and volumes), %d (the shared noise "
        "period) and mixer bits %#04x (A and B's gates) are identical to the tune played alone, "
        "and neither A nor B ever takes the envelope generator"
        % (MIX_SFX, MIX_TUNE, preemption.envelope_frames[0], preemption.envelope_frames[-1],
           preemption.compared_frames, list(CHANNEL_AB_REGS), NOISE_PERIOD_REG, MIXER_AB_GATE_MASK),
        "checks: staging read from the game's own file table and pinned against %s; module "
        "position-independent and master_volume shipped %#04x; every tick flushed registers %s; no "
        "chip read served; every proven loop replayed and compared; mus_%d and sfx_%02d captured "
        "twice and equal; every one of the %d tracks audible in at least one frame; silence agrees "
        "with the render on all of them"
        % (os.path.relpath(GLOBALS_H, PROJECT_DIR), MASTER_VOLUME_SHIPPED, list(TICK_FLUSH_ORDER),
           REPRO_TUNE, REPRO_SFX, len(tracks)),
        "",
        "wrote to %s" % out_dir,
    ))


def sweep():
    """Every track, captured in the order the manifest lists them."""
    tunes = [capture(KIND_MUSIC, number, "mus_%d" % number) for number in range(TUNE_COUNT)]
    effects = [capture(KIND_SFX, number, "sfx_%02d" % number) for number in range(SFX_COUNT)]
    mix = capture(KIND_MIX, MIX_TUNE, "mix_mus%d_sfx%02d" % (MIX_TUNE, MIX_SFX),
                  inject=(MIX_INJECT_FRAME, MIX_SFX))
    return tunes, effects, mix


def main(argv):
    out_dir = argv[1] if len(argv) > 1 else DEFAULT_OUT_DIR
    check_layout_matches_the_reconstruction()
    os.makedirs(out_dir, exist_ok=True)

    with emu.audio_capturing():
        sync = check_tempo_profile()
        tunes, effects, mix = sweep()
        results = tunes + effects + [mix]
        # Everything that can be judged off the register stream is judged BEFORE a byte is written,
        # so a failing run does not leave a directory of files that look like a finished dump.
        check_capture_is_reproducible(tunes, effects)
        for result in results:
            check_loop_replays(result)
        preemption = check_sfx_preempts_channel_c(tunes[MIX_TUNE], mix)
        audible = {result.name: track_audible_frames(result) for result in results}
        check_every_track_is_audible(audible)

        tracks = [Track(result, audible[result.name], write_assets(out_dir, result))
                  for result in results]
        check_silence_agrees_with_the_render(tracks)

    # ...and the manifest last of all, so its presence marks the directory complete.
    header = MANIFEST_HEADER % (MIX_TUNE, MIX_SFX, MIX_INJECT_FRAME, sync, TUNE_FRAME_CAP,
                                SFX_FRAME_CAP)
    with open(os.path.join(out_dir, "manifest.tsv"), "w") as handle:
        handle.write(header + "\t".join(MANIFEST_COLUMNS) + "\n"
                     + "\n".join(manifest_row(track) for track in tracks) + "\n")
    print(report(tracks, sync, preemption, out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
