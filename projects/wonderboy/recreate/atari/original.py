#!/usr/bin/env python3
"""Boot the SHIPPED 1989 disks under Hatari and drive them to a named anchor.

    python3 atari/original.py dump        # the post-boot RAM, at the anchor, with its pins
    python3 atari/original.py neighbour   # ...and the MIS-ANCHOR measurement (see ANCHOR below)
    python3 atari/original.py variance    # ...and how much of it is NOT reproducible (see below)
    python3 atari/original.py frames [N]  # the shipped binary's first N frames, for the side-by-side
    python3 atari/original.py nofire      # NEGATIVE CONTROL: no fire injections -> no anchor
    python3 atari/original.py nodisk2     # NEGATIVE CONTROL: no data disk     -> no anchor

WHY THIS EXISTS. `gen_image.py`'s honesty line says a staged image is a declared fabrication of the
boot's result, and lists the six address ranges this project could not compute: the tile bitmaps,
the depacked overlay, the sprite descriptors and cell data, the eight pre-shifted scroll buffers and
both screens. Two of the routines that produce them ($e67e, `sprites_cru_install` $e87c) are not
merely unported but UNRECONSTRUCTED, so no host-side computation can reach them. The one reference
that can is the ORIGINAL's own RAM, and this file takes it.

RUNTIME ADDRESSES ARE GHIDRA ADDRESSES HERE, uniquely among this workspace's projects, and it is why
no load-base discovery step appears below: `startup_relocate_and_run` copies the body to the FIXED
absolute 0x400 and jumps there (../project.toml argues `load_base = 0x3f8` from exactly that), so
every address in ../names.txt is the address the CPU sees. It is PINNED rather than assumed —
`check_pins` compares a relocation-free window of the dump against the shipped file's own bytes.

============================  WHAT IS INJECTED, AND WHY EACH IS THE HUMAN  ====================

The boot chain is not headless: it stops twice for the player and once for the disk swap. Nothing
here patches the game — three debugger actions stand in for a person at the machine, each fired by
a `:once` breakpoint on the wait's own instruction:

  $e556 / $e55c   the TITLE screen's `clr.b $877 / tst.b $877 / bpl.s` then `tst.b $877 / bmi.s`
                  pair: press fire, release fire. The byte is WB_JOY1_STATE, which the original's
                  own `ikbd_acia_handler` files the joystick report into, so writing $80 to it is
                  the report a pushed stick would have produced.
  $e5ae / $e5b4   the CREDITS screen's identical pair.
  $e5ba           `stage_sequence_advance`'s first instruction, the last one before the overlay
                  load at $e5fa. Disk 1 carries only SWB.PRG, TITLESCR.RAD and CREDITS.RAD; every
                  overlay, TILEDATA.RAD and SPRITES.CRU are on disk 2. So the disk is swapped here,
                  which is what `show_data_disk_prompt` ($e494) asks a player to do.

BOTH ARE CONTROLLED. `nofire` and `nodisk2` remove one injection each and the anchor must NOT be
reached; without them "the boot ran" would rest on the injections being necessary rather than on
their being measured to be. (Measured: no fire leaves the machine on the title screen for as long
as it is given; no disk 2 hangs inside `load_resource_by_index`, which retries rather than failing
over to the prompt.)

===============================  THE ANCHOR, AND ITS MIS-ANCHOR  ==============================

Two addresses in the image hold `jmp $4a0.w`, $e708 and $f8b4. **ONLY $f8b4 IS LIVE**, and this file
uses it: $e6fc is `bsr.w $f89e`, $f89e falls off its own end into $f8b4's `jmp`, so the `bsr` never
returns and $e700/$e708 are dead. `../names.txt` cmt 0x4a0 listed both as entries until batch 43
phase B and now records this.

THE CENSUS BEHIND THAT, AT ITS FULL WIDTH — because a recipe narrower than its conclusion is how the
operand-hiding forms of batches 28 and 31 got missed twice. Every even offset of the relocated image
was scanned for: absolute LONG operands; bare words equal to the target; Bcc/BRA/BSR 8- AND 16-bit
displacements; DBcc 16-bit displacements; and EVERY `(d16,PC)` form — `jmp`, `jsr`, `lea`, `pea` and
any other extension-word-bearing opcode — resolved against the extension word's own address.

  $e708   ZERO hits under every form above.
  $e700   two bare words equal $e700, and NEITHER can be a reference. $ebb2 is the instruction
          `asl.b #3,d0`; $fbc6 is the low half of the immediate in `move.l #$4e700,$82b2.l`, a
          scroll-buffer address. And an absolute-SHORT operand sign-extends, so a 16-bit $e700 names
          $ffffe700 and could never reach $00e700 whatever it were part of.

AN ANCHOR IS ONLY EVIDENCE IF A MIS-ANCHOR IS DETECTABLE, so the neighbour is measured rather than
asserted to be different: `neighbour` dumps at $e6fc — the instruction that calls the stage load —
and reports how many bytes of the game-owned span differ from the $f8b4 dump. They are the whole
product of `stage_load_window`, so the two moments are hundreds of kilobytes apart and a one-anchor
slip could not pass for a hit.

The anchor is additionally pinned FROM THE INSIDE by state only a completed boot can leave —
`check_pins` — so a dump taken at the right PC of a run that went wrong still fails.

==========================  THE DUMP IS NOT BIT-REPRODUCIBLE, AND BY HOW MUCH  ================

Two dumps at the same PC of the same disks are NOT the same bytes, and a staged image that pretends
otherwise would be a fixture. `variance` measures it — two independent boots, differenced.

**THIS FILE OWNS THE FIGURE AND THE FIGURE MOVES.** Four boots measured 536, 538, 591 and 605 of
523,272 bytes, so what is true is a RANGE of roughly 500-650 and not any one of them; `variance`
prints the current reading and writes it to `build/VARIANCE.txt`, and every other surface
(atari/README.md, STATUS.md) cites this mode rather than restating a number that would be stale on
the next boot. It decomposes into four bands and nothing else, and each band carries a CEILING as
well as a range — a band is a weak guard on its own, since the sound band spans 13,604 bytes to
certify a couple of dozen:

  $f314..$f514   512 of them, every time, and they are the whole reason this mode exists. The
                 Copylock WRITES that band at run time and writes something DIFFERENT every boot:
                 the bytes are a descending, wrapping sequence, i.e. its own trace/timing samples
                 rather than code it recovered. So the band is not data, and staging it stages one
                 boot's scratch. It is inert here — no reconstructed function lies between
                 `copylock_illegal_handler` ($ee02) and `copylock_restore_state` ($f542), and
                 nothing under `../src/` ever reads there — but a claim that the image is "the
                 original's memory" has to say which of its bytes are one run's accident.
  $17adc..$1b000 12-22 bytes of the sound module's own state: a song is playing at the anchor and
                 its driver's cursors depend on which vblank the boot finished on. The bytes seen
                 moving sit in a much narrower run inside the band (~$17be4..$1aaea).
  $7f000..$80000 8-72 bytes of the game's stack, below its `movea.l #$80000,a7`.
  $74a           0 or 1 — WB_VBL_COUNTER, which vblank the boot happened to finish on. THE GUARD
                 FOUND THIS ONE: the first draft of the band table did not have it, the second boot
                 landed on a different count, and the mode named the address rather than passing.

WHAT THAT COSTS A FRAME DIFFERENTIAL, stated before it is spent: a comparison against a FRESH boot
of the original can only be exact for surfaces none of those bytes reaches. The framebuffer and
the sixteen pens are such surfaces — the Copylock band is never read, the sound state reaches the
YM2149 and not the shifter, and the stack is the boot's. A whole-memory comparison is not.
"""
import hashlib
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE.parent
sys.path.insert(0, str(REC / "test"))
from layout import wb                                            # noqa: E402

BIN = REC.parents[0] / "bin"
BUILD = HERE / "build"
OUT = HERE / "out"

# ---- the shipped disks ------------------------------------------------------------------------
# Pasti .stx, the uncracked Activision release. The names carry spaces and brackets, and HATARI'S
# DEBUGGER SPLITS `setopt` ON WHITESPACE — measured: it reported `Image '...(1989)(Activision)' not
# found` and carried on — so every run symlinks them into a temporary directory under a plain name.
DISK1 = BIN / "Wonderboy in Monsterland (1989)(Activision)(Disk 1 of 2)[a][!].stx"
DISK2 = BIN / "Wonderboy in Monsterland (1989)(Activision)(Disk 2 of 2)[a][!].stx"

# ---- the boot chain's own addresses, from out/wonderboy_dis.txt ---------------------------------
# Runtime == Ghidra (see the header). Each is the instruction quoted beside it.
TITLE_FIRE_PRESS_PC = 0xe556      # `tst.b $877.w`  / `bpl.s $e556` — wait for the stick's bit 7
TITLE_FIRE_RELEASE_PC = 0xe55c    # `tst.b $877.w`  / `bmi.s $e55c` — ...and for it to go away
CREDITS_FIRE_PRESS_PC = 0xe5ae    # the same pair after CREDITS.RAD
CREDITS_FIRE_RELEASE_PC = 0xe5b4
DATA_DISK_SWAP_PC = 0xe5ba        # `clr.w $6ef0.w`, stage_sequence_advance's first instruction
STAGE_LOAD_CALL_PC = 0xe6fc       # `bsr.w $f89e` — the NEIGHBOUR anchor, one call before the frame
BOOT_ANCHOR_PC = 0xf8b4           # `jmp $4a0.w` — THE ANCHOR: the boot's last instruction

FIRE_DOWN = 0x80                  # bit 7 of the IKBD joystick report; ../include/wonderboy.h:141
FIRE_UP = 0x00
FIRST_HIT = 1                     # Hatari's hit counter is 1-based AND it rejects an explicit `:1`

# ---- the game's own address space ---------------------------------------------------------------
# What a staged image has to carry, and it is bounded by ../project.toml's three agreeing readings:
# `movea.l #$80000,a7` in hw_init_vectors, a screen clear covering exactly $70000..$7fd00, and no
# longword constant in the image at or above $80000. Below WB_STAGED_AT is the 68000 vector page,
# which belongs to whoever owns the machine and not to the image.
GAME_SPAN_END = 0x80000
WB_STAGED_AT = int(re.search(r"^load_base\s*=\s*(0x[0-9a-fA-F]+)",
                             (REC / "project.toml").read_text(), re.M).group(1), 16)

# ---- Hatari ---------------------------------------------------------------------------------
MEMSIZE_MB = 4
RAM_BYTES = MEMSIZE_MB << 20
# The measured boot: fire at VBL ~1200 and ~1370, overlay depacked at 1415, tiles installed at 1750,
# SPRITES.CRU installed at 2819, the anchor at 2854. 12000 is four times the whole chain, which is
# the margin the CONTROLS need — "the anchor was not reached" only means something if the run was
# long enough to reach it. The floppy is emulated at its real speed (no --fastfdc: the Copylock
# reads the disk itself, and speeding the FDC up is documented to break exactly that class).
RUN_VBLS = 12000
RUN_TIMEOUT = 600
DUMP_FILE = "ORIGRAM.BIN"
REGISTERS_FILE = "ORIGREGS.txt"
PENS_FILE = "ORIGPENS.BIN"
# The shifter's sixteen colour registers, in the 32-bit form the debugger reads I/O space at. The
# register NUMBER has one definition — the reconstruction's own 24-bit WB_SHIFTER_PALETTE — and the
# high byte is the I/O page a 68000's address bus ignores. wonderboy_main.c derives its spelling the
# same way, from the same constant.
SHIFTER_IO_PAGE = 0xff000000
SHIFTER_PALETTE = SHIFTER_IO_PAGE | wb("SHIFTER_PALETTE")
PALETTE_PENS = wb("PALETTE_COLOURS")
PALETTE_BYTES = PALETTE_PENS * 2
# The ST implements THREE bits per gun; the fourth bit of each nibble does not exist and a CPU read
# of a colour register returns it as whatever was last on the bus. So OUR side's pens (read by the
# program) carry that noise and the shipped side's (read by `savebin`, straight out of Hatari's
# register model) do not — masking it is the only way to compare the two reads honestly, and
# everything the machine can display is inside the mask. THE ONE PYTHON DEFINITION: smoke.py imports
# it from here rather than keeping its own, and wonderboy_main.c's ST_PEN_MASK is the C spelling.
ST_PEN_MASK = 0x0777


def pen_words(blob):
    """The sixteen pens of a 32-byte palette dump, masked to the bits the hardware has."""
    return [word & ST_PEN_MASK for word in struct.unpack(">%dH" % PALETTE_PENS, blob)]
ANCHOR_BEACON = "ANCHOR_REACHED"
REGISTERS_BEACON = "REGISTERS_DUMPED"

HATARI_BANNER_RE = re.compile(r"Hatari v\d|WARN :|INFO :|Reading TOS")
FAULT_RE = re.compile(r"(Bus [Ee]rror|Address [Ee]rror|CPU halted|double bus)")
FAULT_PC_RE = re.compile(r"PC=(\$[0-9a-fA-F]+)")
# TOS sizes memory by faulting on purpose. Excused by the EXACT PC of the probe, never by "the PC is
# in ROM": a stale vector sends the CPU into ROM code, so a range test would excuse the very class
# this scan is for. smoke.py carries the same two and for the same reason.
MEMORY_PROBE_PCS = ("$e00d98", "$fc0174")


def find_tos():
    named = os.environ.get("WB_TOS_ROM")
    if named:
        return named
    for candidate in sorted((HERE.parents[3] / "tools" / "hatari").glob("TOS*.img"), reverse=True):
        return str(candidate)
    return None


def action_file(directory, name, *commands):
    """Write one breakpoint's action file and return the `:file` clause that runs it.

    These are HOST paths the debugger reads and writes; they are deliberately not on any emulated
    drive, where the game could see them."""
    path = directory / name
    path.write_text("".join(command + "\n" for command in commands) + "cont\n")
    return f":file {path}"


def poke_byte(addr, value):
    return f"w b ${addr:x} ${value:x}"


def boot_script(directory, disk2, extra_stops=()):
    """The debugger script that carries the shipped binary from power-on to the frame loop.

    `extra_stops` is a list of (pc, hit, action-file name, [command, ...]) the caller anchors its own
    work at — one breakpoint per anchor, whose action file does all of that anchor's work. Shared by
    the dump below and by smoke.py's frame differential, so the injections that make the shipped
    side comparable have ONE spelling and cannot drift between the two runs that are compared.

    `hit` is which arrival at `pc` to stop on, 1-based as Hatari counts them. THE GUARD BELOW KEYS ON
    THE PAIR AND NOT ON THE PC, which is not a detail: the frame differential deliberately sets N
    breakpoints on the SAME address ($4a0, once per frame) told apart by their counts, so a guard
    keyed on the address alone would reject the harness's own scripts — and its first draft did not
    see them at all, because `frames_script` built those lines itself and went round it. What must
    not recur is two breakpoints selecting the SAME arrival: their counters interfere, and the
    measured consequence in the sibling project was captures and dumps arriving from different
    moments and being compared as if from one."""
    joy1 = wb("JOY1_STATE")
    lines = [
        f"b pc = ${TITLE_FIRE_PRESS_PC:x} :once :quiet "
        + action_file(directory, "FIRE1D.INI", "echo TITLE_FIRE_DOWN", poke_byte(joy1, FIRE_DOWN)),
        f"b pc = ${TITLE_FIRE_RELEASE_PC:x} :once :quiet "
        + action_file(directory, "FIRE1U.INI", "echo TITLE_FIRE_UP", poke_byte(joy1, FIRE_UP)),
        f"b pc = ${CREDITS_FIRE_PRESS_PC:x} :once :quiet "
        + action_file(directory, "FIRE2D.INI", "echo CREDITS_FIRE_DOWN", poke_byte(joy1, FIRE_DOWN)),
        f"b pc = ${CREDITS_FIRE_RELEASE_PC:x} :once :quiet "
        + action_file(directory, "FIRE2U.INI", "echo CREDITS_FIRE_UP", poke_byte(joy1, FIRE_UP)),
    ]
    if disk2 is not None:
        lines.append(f"b pc = ${DATA_DISK_SWAP_PC:x} :once :quiet "
                     + action_file(directory, "SWAP.INI", "echo DATA_DISK_INSERTED",
                                   f"setopt --disk-a {disk2}"))
    if len({(pc, hit) for pc, hit, _, _ in extra_stops}) != len(extra_stops):
        raise SystemExit("two breakpoints select the same arrival at the same PC: their counters "
                         "interfere, and the anchors would fire at moments other than the ones "
                         "asked for. Give each anchor ONE breakpoint whose action file does all of "
                         "that anchor's work.")
    for pc, hit, name, commands in extra_stops:
        # Hatari counts hits from 1 and REJECTS an explicit `:1`, so the first arrival is a bare
        # `:once`. That is a parser quirk of the debugger, not a choice.
        count = "" if hit == FIRST_HIT else f":{hit} "
        lines.append(f"b pc = ${pc:x} {count}:once :quiet "
                     + action_file(directory, name, *commands))
    return "\n".join(lines) + "\n"


def run_original(build_script, tag, run_vbls=RUN_VBLS, fires=True):
    """Boot disk 1 and run `build_script(directory, disk2_path)` against it.

    Returns (produced files, merged Hatari output, exit status). THE STREAMS ARE MERGED because
    Hatari writes its logging AND all debugger output to stderr; a parser reading stdout scans an
    empty string for ever, which is a measured year-long blindness in the sibling project."""
    rom = find_tos()
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name, image in (("d1.stx", DISK1), ("d2.stx", DISK2)):
            if not image.exists():
                raise SystemExit(f"{image} is missing — this mode needs the shipped .stx disks")
            (directory / name).symlink_to(image)
        script = build_script(directory, directory / "d2.stx")
        if not fires:
            script = "\n".join(line for line in script.splitlines() if "FIRE" not in line) + "\n"
        (directory / "CMD.INI").write_text(script)
        args = ["hatari", "--sound", "off", "--fast-forward", "on", "--confirm-quit", "off",
                "--statusbar", "off", "--memsize", str(MEMSIZE_MB), "--monitor", "rgb",
                "--run-vbls", str(run_vbls), "--disk-a", str(directory / "d1.stx"),
                "--parse", str(directory / "CMD.INI")]
        if rom:
            args[1:1] = ["--tos", rom]
        env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
        done = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=RUN_TIMEOUT)
        # ONE LOG PER MODE, kept whether the mode passed or not. A single shared filename would let
        # the control's run overwrite the dump's, and the two are read together when a mode is
        # argued about.
        OUT.mkdir(exist_ok=True)
        (OUT / f"original-{tag}.log").write_text(done.stdout)
        if not HATARI_BANNER_RE.search(done.stdout):
            raise SystemExit(f"FAIL: Hatari's output carries none of its own logging (status "
                             f"{done.returncode}) — every check below would read an empty string")
        produced = {path.name: path.read_bytes()
                    for path in directory.iterdir() if path.suffix.upper() == ".BIN"}
        return produced, done.stdout, done.returncode


def machine_faults(log):
    """The log's faults, minus TOS's own memory-sizing probe, by EXACT PC."""
    faults = []
    for line in log.splitlines():
        if not FAULT_RE.search(line):
            continue
        where = FAULT_PC_RE.search(line)
        if where and where.group(1) in MEMORY_PROBE_PCS:
            continue
        faults.append(line.strip())
    return faults


# ---- the pins ------------------------------------------------------------------------------
# WHAT MAKES THIS DUMP THE RIGHT MOMENT, from the inside. Each is state the shipped .PRG does NOT
# carry and only a completed boot leaves, so a dump of a run that went wrong fails here even though
# its PC was right. The addresses come from ../include/wonderboy.h through layout.py; the values are
# the boot's own operands, quoted from out/wonderboy_dis.txt.
VEC_LEVEL4_VBL = 0x70
VEC_MFP_ACIA = 0x118
VBL_HANDLER_PC = 0x716            # `move.l #$716,$70.w` — hw_init_vectors ($f8bc), and again $e506
ACIA_HANDLER_PC = 0x754           # `move.l #$754,$118.w` — the same routine
RESOURCE_SIGNATURE = 0x45         # 'E', stamped by resource_table_relocate ($fe1e). NOT idempotent,
                                  # which is what the signature exists for, and zero in the .PRG.
STAGE_START_PTR_VALUE = 0x217d8   # `lea $217d8.l,a1` at $f8aa, latched by stage_load_window
FIRST_STAGE_NUMBER = 1            # level_seq_table[0][3] -> $bd88; the first playable stage

# A window of the program body with no relocation site in it and no runtime writer: what makes the
# dump's addresses comparable with ../names.txt's at all. Chosen inside game_main_loop's own code,
# which is executed and never written.
CODE_WINDOW = (0x4a0, 0x50a)


def check_pins(ram, prg_image):
    """(problems, notes) for a dump that claims to be the original's post-boot RAM."""
    def long_at(addr):
        return struct.unpack(">I", ram[addr:addr + 4])[0]

    def word_at(addr):
        return struct.unpack(">H", ram[addr:addr + 2])[0]

    lo, hi = CODE_WINDOW
    pins = [
        ("the program is at its Ghidra addresses", bytes(prg_image[lo:hi]) == ram[lo:hi],
         f"{hi - lo} bytes of game_main_loop's own code at {lo:#x}"),
        ("the VBL vector holds vbl_handler", long_at(VEC_LEVEL4_VBL) == VBL_HANDLER_PC,
         f"${VEC_LEVEL4_VBL:x} = {long_at(VEC_LEVEL4_VBL):#x}, want {VBL_HANDLER_PC:#x}"),
        ("the ACIA vector holds ikbd_acia_handler", long_at(VEC_MFP_ACIA) == ACIA_HANDLER_PC,
         f"${VEC_MFP_ACIA:x} = {long_at(VEC_MFP_ACIA):#x}, want {ACIA_HANDLER_PC:#x}"),
        ("the resource table is relocated", ram[wb("RESOURCE_HEADER")] == RESOURCE_SIGNATURE,
         f"{wb('RESOURCE_HEADER'):#x} = {ram[wb('RESOURCE_HEADER')]:#04x}, want "
         f"{RESOURCE_SIGNATURE:#04x} ('E')"),
        ("stage_load_window latched the map", long_at(wb("STAGE_MAP_PTR")) == wb("MAP_ROW_STRIDE"),
         f"{wb('STAGE_MAP_PTR'):#x} = {long_at(wb('STAGE_MAP_PTR')):#x}, want "
         f"{wb('MAP_ROW_STRIDE'):#x}"),
        ("...and the start record", long_at(wb("STAGE_START_PTR")) == STAGE_START_PTR_VALUE,
         f"{wb('STAGE_START_PTR'):#x} = {long_at(wb('STAGE_START_PTR')):#x}, want "
         f"{STAGE_START_PTR_VALUE:#x}"),
        ("the first stage is loaded", word_at(0xbd88) == FIRST_STAGE_NUMBER,
         f"stage number = {word_at(0xbd88)}, want {FIRST_STAGE_NUMBER}"),
    ]
    problems = [f"{name} ({detail})" for name, ok, detail in pins if not ok]
    return problems, [f"{'ok  ' if ok else 'FAIL'} {name}: {detail}" for name, ok, detail in pins]


# ---- the modes -------------------------------------------------------------------------------

def dump_at(pc, tag):
    """Run the shipped disks to `pc` and return the whole of RAM there, or None."""
    def script(directory, disk2):
        return boot_script(directory, disk2, extra_stops=[
            (pc, FIRST_HIT, "ANCHOR.INI", [f"echo {ANCHOR_BEACON}",
                                f"savebin {directory / DUMP_FILE} 0 {RAM_BYTES:#x}",
                                # THE ENTRY REGISTERS ARE PART OF THE MOMENT. `game_main_loop` is
                                # `jmp`ed into, not called, so the frame it runs inherits whatever
                                # the boot left — and its one C argument, `sprite_pass_regs`, is
                                # exactly that inheritance (blit.h: a5 is a real input).
                                # ...AND THE SIXTEEN PENS, which are the boot's product too and do
                                # NOT live in RAM. `set_palette` runs inside the unported boot
                                # chain, so a build that stages only memory paints its frame
                                # through whatever the DESKTOP left in the shifter — measured on
                                # the first M2 run, which came back with TOS 1.04's own palette.
                                f"savebin {directory / PENS_FILE} ${SHIFTER_PALETTE:x} "
                                f"{PALETTE_BYTES}",
                                "cpureg", f"echo {REGISTERS_BEACON}"])])

    produced, log, status = run_original(script, tag)
    print(f"-- {tag}: anchor ${pc:x}, hatari exit={status} "
          f"(full log in {OUT / ('original-%s.log' % tag)})")
    faults = machine_faults(log)
    if faults:
        raise SystemExit("FAIL: unhealthy machine: " + " | ".join(faults[:4]))
    if ANCHOR_BEACON not in log:
        return None, None, None
    return produced.get(DUMP_FILE), registers_at_anchor(log), produced.get(PENS_FILE)


# `cpureg`'s block, between the two beacons the action file brackets it with. Kept VERBATIM as the
# evidence and parsed for the one register the port needs, rather than parsed into a dict nobody
# reads: which registers matter is `../include/blit.h`'s question, not this file's.
REGISTER_RE = re.compile(r"\b([DA][0-7])\s*[:=]?\s*\$?([0-9a-fA-F]{8})\b")


def registers_at_anchor(log):
    """The `cpureg` text the anchor printed, or None."""
    start = log.find(ANCHOR_BEACON)
    end = log.find(REGISTERS_BEACON, start + 1)
    if start < 0 or end < 0:
        return None
    return log[start + len(ANCHOR_BEACON):end]


def register(text, name):
    for found, value in REGISTER_RE.findall(text or ""):
        if found == name:
            return int(value, 16)
    return None


def shipped_image():
    sys.path.insert(0, str(HERE.parents[3] / "tools"))
    from recreate_kit import project
    project.load(REC)
    import loader
    return loader.load_image(str(BIN / "disk1" / "AUTO" / "SWB.PRG")), loader.PROGRAM_END


def mode_dump():
    ram, registers, pens = dump_at(BOOT_ANCHOR_PC, "dump")
    if ram is None:
        raise SystemExit(f"FAIL: the boot never reached ${BOOT_ANCHOR_PC:x}")
    image, program_end = shipped_image()
    problems, notes = check_pins(ram, image)
    for note in notes:
        print(f"   {note}")
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))

    # EVERY CHECK BEFORE EVERY WRITE, and that ordering is the whole point.
    #
    # The three artefacts are ONE MEASUREMENT of ONE BOOT, and `build.sh m2`'s precondition can only
    # see whether each file exists. An earlier draft wrote the RAM, then validated the registers,
    # then wrote them, then validated the palette — so a boot whose `cpureg` block did not parse
    # left THIS boot's RAM beside the PREVIOUS boot's registers and palette. All three exist, the
    # build proceeds, and the image and A5 come from one boot while the sixteen pens come from
    # another; the resulting frame mismatch reads as a rendering bug. Validate all three, then
    # write all three.
    unwind = register(registers, "A5") if registers else None
    if registers is None or unwind is None:
        raise SystemExit("FAIL: the anchor dumped memory but no readable register file — "
                         "`game_main_loop`'s entry state would then be chosen here, not measured")
    if pens is None or len(pens) != PALETTE_BYTES:
        raise SystemExit(f"FAIL: the anchor did not dump {PALETTE_BYTES} bytes of palette — a frame "
                         f"staged without it is painted through whoever owned the shifter last")

    span = ram[WB_STAGED_AT:GAME_SPAN_END]
    BUILD.mkdir(exist_ok=True)
    # Identifies THIS boot's set of three. A digest of the three payloads rather than a clock: two
    # boots a second apart must get different ids, and two boots that somehow produced identical
    # bytes are the same measurement and may share one.
    boot_id = hashlib.sha256(span + registers.encode() + pens).hexdigest()[:16]
    # The manifest is stamped AFTER all three land, so an interrupted set has no manifest to match.
    (BUILD / MANIFEST_FILE).unlink(missing_ok=True)
    (BUILD / DUMP_FILE).write_bytes(span)
    (BUILD / REGISTERS_FILE).write_text(registers)
    (BUILD / PENS_FILE).write_bytes(pens)
    print(f"{write_manifest(boot_id)}: stamps this boot over "
          f"{', '.join(MANIFEST_ARTEFACTS)}")
    print(f"{BUILD / REGISTERS_FILE}: the entry register file, A5 (the sprite pass's `unwind`) = "
          f"{unwind:#010x}")
    print(f"{BUILD / PENS_FILE}: the sixteen pens the boot left — " + " ".join(
        "%03x" % pen for pen in pen_words(pens)))
    print(f"{BUILD / DUMP_FILE}: {len(span)} bytes "
          f"[{WB_STAGED_AT:#x},{GAME_SPAN_END:#x}) — the game's whole address space at the anchor")
    same = sum(1 for i in range(WB_STAGED_AT, program_end) if image[i] == ram[i])
    print(f"program span [{WB_STAGED_AT:#x},{program_end:#x}): {same} of "
          f"{program_end - WB_STAGED_AT} bytes are the shipped file's own "
          f"({program_end - WB_STAGED_AT - same} differ — see gen_image.py's provenance table)")
    return True


# How far above the measured boot-to-boot noise a mis-anchor has to sit before it counts as
# DETECTABLE. Ten times: the noise is ~600 bytes and the real margin is ~134,000, so the factor is
# not tuned to squeeze a pass — it is loose enough to be obviously satisfied and tight enough that a
# same-moment pair (which sits AT the noise) cannot clear it.
MIS_ANCHOR_FLOOR_MULTIPLE = 10


def span_difference(first, second):
    """How many bytes of two staged spans differ."""
    return sum(1 for a, b in zip(first, second) if a != b)


def mode_neighbour():
    """THE MIS-ANCHOR MEASUREMENT, against the noise floor the instrument actually measures.

    AN EARLIER DRAFT ASSERTED `differ == 0` AND COULD NEVER FIRE. Two dumps of the SAME moment
    already differ by ~600 bytes (the copylock's scratch alone is 512), so "not byte-identical" is
    true of every pair this tool can produce, including two boots stopped at the same instruction.
    The assertion passed for the right reason and would have passed for the wrong one.

    So the floor is derived from `mode_variance`'s reading and CHECKED IN BOTH DIRECTIONS in one
    run: the real mis-anchor must clear it, and a pair the instrument knows is the SAME moment —
    the two same-anchor boots variance already differenced — must not. Without the second half the
    floor is a number nobody has shown is discriminating."""
    anchor = BUILD / DUMP_FILE
    same_moment = BUILD / SECOND_DUMP_FILE
    reading = BUILD / VARIANCE_FILE
    for needed in (anchor, same_moment, reading):
        if not needed.exists():
            raise SystemExit(f"run `original.py dump` and then `original.py variance` first — "
                             f"{needed} is what this measures against")
    noise = int(reading.read_text().strip())
    floor = noise * MIS_ANCHOR_FLOOR_MULTIPLE
    at_anchor = anchor.read_bytes()

    ram, _, _ = dump_at(STAGE_LOAD_CALL_PC, "neighbour")
    if ram is None:
        raise SystemExit(f"FAIL: the boot never reached ${STAGE_LOAD_CALL_PC:x}")
    before = ram[WB_STAGED_AT:GAME_SPAN_END]

    differ = span_difference(at_anchor, before)
    control = span_difference(at_anchor, same_moment.read_bytes())
    print(f"   boot-to-boot noise at the SAME anchor: {noise} bytes, so the floor is "
          f"{MIS_ANCHOR_FLOOR_MULTIPLE}x that = {floor}")
    print(f"   ${STAGE_LOAD_CALL_PC:x} (the `bsr.w $f89e` one call before the frame loop) against "
          f"${BOOT_ANCHOR_PC:x}: {differ} of {len(at_anchor)} bytes differ "
          f"({100.0 * differ / len(at_anchor):.1f}%)")
    print(f"   ...and the SAME-MOMENT control, two boots both stopped at ${BOOT_ANCHOR_PC:x}: "
          f"{control} bytes differ ({100.0 * control / len(at_anchor):.2f}%)")

    problems = []
    if differ <= floor:
        problems.append(f"the mis-anchor moved only {differ} bytes, at or under the {floor}-byte "
                        f"floor — a one-anchor slip is indistinguishable from boot-to-boot noise "
                        f"and the anchor is not evidence of anything")
    if control > floor:
        problems.append(f"two dumps of the SAME moment differ by {control} bytes, ABOVE the "
                        f"{floor}-byte floor — the floor does not separate a different moment from "
                        f"the same one, so clearing it means nothing")
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))
    print(f"OK: a one-call mis-anchor clears the floor by {differ / max(floor, 1):.0f}x and the "
          f"same moment does not reach it — the margin discriminates in both directions")
    return True


# THE BANDS THE IRREPRODUCIBLE BYTES MUST FALL IN, each with A CEILING ON HOW MANY.
#
# A band alone is a weak guard: the sound band spans 13,604 bytes to certify ~20, and the stack band
# 4,096 to certify ~69, so "it landed inside a named band" would stay true while the count grew a
# hundredfold. The header's claim is that the variance DECOMPOSES into these four and nothing else,
# and a claim that cannot be falsified is not one — so each band carries a ceiling set from the
# measured readings with headroom, and `mode_variance` reds on a band that grows into its slack as
# loudly as on a byte outside every band.
#
# (name, start, end, ceiling). Readings across four boots: copylock exactly 512 every time (it is a
# fixed-size scratch and the whole band turns over), sound 20-22, stack 56-72, counter 0-1.
VARIANCE_BANDS = (
    ("the copylock's scratch", 0xf314, 0xf514, 512),
    # The sound module's own span, `../project.toml`'s `0x17adc..0x1ab04` rounded up to the next
    # page. The bytes actually seen moving are a much narrower run inside it (~$17be4..$1aaea), and
    # the ceiling rather than the band is what pins the size.
    ("the sound module's state", 0x17adc, 0x1b000, 256),
    # The game sets its own A7 to $80000 and grows down; the deepest byte seen moving is ~$7ff0d.
    ("the game's stack", 0x7f000, GAME_SPAN_END, 512),
    # WHICH VBLANK THE BOOT FINISHED ON. The most obvious irreproducible word in the image and the
    # one this table was written without — the guard below found it and named the address. It is a
    # PHASE and not content: `flip_screen`'s two waits compare against it, so a frame differential
    # inherits an offset in the counter and not a difference in what is drawn.
    ("vbl_handler's counter", wb("VBL_COUNTER"), wb("VBL_COUNTER") + 2, 2),
)

# The second same-anchor boot and the reading it produced, kept for `mode_neighbour`'s floor: the
# mis-anchor margin is only meaningful against the noise this instrument actually measures.
SECOND_DUMP_FILE = "ORIGRAM2.BIN"
VARIANCE_FILE = "VARIANCE.txt"

# ---- the boot manifest -------------------------------------------------------------------------
#
# THE THREE ARTEFACTS ARE ONE MEASUREMENT OF ONE BOOT, AND FILE-EXISTENCE CANNOT SAY SO. Validating
# all three before writing any of them narrows the window; it does not close it — three `write_bytes`
# calls are three moments, and an interrupt (or a full disk, or a Ctrl-C) between the first and the
# third leaves THIS boot's RAM beside the PREVIOUS boot's registers and palette. All three exist,
# `build.sh m2`'s `-f` test is satisfied, and the image and A5 come from one boot while the sixteen
# pens come from another — a frame mismatch that reads as a rendering bug.
#
# So the boot stamps a manifest: an id for the boot plus the size and digest of each artefact,
# WRITTEN LAST. `build.sh m2` verifies the three against it and refuses on any mismatch, so a
# half-written set is a loud refusal rather than a plausible build. The manifest being last is what
# makes it work — an interrupted run leaves no manifest, or an older one whose digests do not match.
MANIFEST_FILE = "ORIGBOOT.txt"
MANIFEST_ARTEFACTS = (DUMP_FILE, REGISTERS_FILE, PENS_FILE)


def artefact_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_manifest(boot_id):
    lines = [f"boot {boot_id}"]
    for name in MANIFEST_ARTEFACTS:
        path = BUILD / name
        lines.append(f"{name} {path.stat().st_size} {artefact_digest(path)}")
    (BUILD / MANIFEST_FILE).write_text("\n".join(lines) + "\n")
    return BUILD / MANIFEST_FILE


def check_manifest(build_dir):
    """(ok, message) for the artefact set in `build_dir`. Used by build.sh before an m2 build."""
    manifest = Path(build_dir) / MANIFEST_FILE
    if not manifest.exists():
        return False, (f"{manifest} is missing — the dump did not finish, or predates the manifest. "
                       f"Run `python3 atari/original.py dump`.")
    rows = [line.split() for line in manifest.read_text().split("\n") if line.strip()]
    boot = next((row[1] for row in rows if row[0] == "boot"), None)
    seen = {row[0]: (int(row[1]), row[2]) for row in rows if row[0] != "boot"}
    if set(seen) != set(MANIFEST_ARTEFACTS):
        return False, f"{manifest} lists {sorted(seen)}, expected {sorted(MANIFEST_ARTEFACTS)}"
    for name, (size, digest) in seen.items():
        path = Path(build_dir) / name
        if not path.exists():
            return False, f"{path} is missing although boot {boot} recorded it"
        if path.stat().st_size != size or artefact_digest(path) != digest:
            return False, (f"{path} does not match boot {boot}'s manifest — the three artefacts are "
                           f"ONE measurement of ONE boot and this set is mixed or half-written. "
                           f"Re-run `python3 atari/original.py dump`.")
    return True, f"boot {boot}: all {len(seen)} artefacts match the manifest"


def mode_variance():
    """HOW MUCH OF THE DUMP IS ONE BOOT'S ACCIDENT: two independent boots, differenced.

    THE INSTRUMENT THAT OWNS THE NUMBER. Every other surface — this file's header, atari/README.md,
    STATUS.md — cites the range this mode measures rather than restating a figure of its own, because
    the figure MOVES between boots and three copies of a moving number are three chances to quote a
    stale one."""
    first = BUILD / DUMP_FILE
    if not first.exists():
        raise SystemExit(f"run `original.py dump` first — {first} is one of the two boots")
    ram, _, _ = dump_at(BOOT_ANCHOR_PC, "variance")
    if ram is None:
        raise SystemExit(f"FAIL: the second boot never reached ${BOOT_ANCHOR_PC:x}")
    a, b = first.read_bytes(), ram[WB_STAGED_AT:GAME_SPAN_END]
    differ = [i + WB_STAGED_AT for i, (x, y) in enumerate(zip(a, b)) if x != y]
    print(f"   two independent boots differ in {len(differ)} of {len(a)} bytes")

    problems = []
    unexplained = list(differ)
    for name, start, end, ceiling in VARIANCE_BANDS:
        inside = [i for i in differ if start <= i < end]
        unexplained = [i for i in unexplained if not (start <= i < end)]
        print(f"     {name} [{start:#x},{end:#x}): {len(inside)} of at most {ceiling}")
        if len(inside) > ceiling:
            problems.append(f"{name} moved {len(inside)} bytes, past its {ceiling}-byte ceiling — "
                            f"the band still contains them but the decomposition no longer "
                            f"describes them")
    if unexplained:
        problems.append(f"{len(unexplained)} bytes differ outside every band this file knows about, "
                        f"first at {unexplained[0]:#x} — the decomposition in the header is "
                        f"incomplete and the staged image carries an unnamed accident")
    if problems:
        raise SystemExit("FAIL: " + "; ".join(problems))

    # KEPT FOR `mode_neighbour`, which needs both: the reading, to set a floor the mis-anchor has to
    # clear, and the second boot itself, to check that floor in the other direction.
    (BUILD / SECOND_DUMP_FILE).write_bytes(b)
    (BUILD / VARIANCE_FILE).write_text(f"{len(differ)}\n")
    print(f"OK: every irreproducible byte is inside a named band and under its ceiling; none of "
          f"them reaches a frame ({BUILD / VARIANCE_FILE} records the reading)")
    return True


# WHICH frames to photograph, READ OUT OF THE SHIM rather than restated: the two sides have to be
# anchored at the same frames, and a list written down twice is a comparison of two different
# moments waiting to happen (CLAUDE.md §5). wonderboy_main.c argues the choice.
def anchor_frames():
    line = re.search(r"^#define M2_ANCHOR_FRAMES (.+)$",
                     (HERE / "wonderboy_main.c").read_text(), re.M)
    if not line:
        raise SystemExit("wonderboy_main.c no longer defines M2_ANCHOR_FRAMES — the two sides' "
                         "anchors have no shared definition, so nothing below compares one moment")
    return [int(frame) for frame in line.group(1).split(",")]


FRAME_LOOP_PC = 0x4a0             # `game_main_loop` — one entry per frame, and nothing else reaches
                                  # it (../names.txt cmt 0x4a0: `jmp $4a0.w` from $f8b4, `bra.s`
                                  # from $508). So the Nth hit IS the Nth frame's start.
SCREEN_REGION = (0x70000, 0x80000)  # both 32000-byte screens and the game's stack, in one savebin


def frames_script(directory, disk2, frames):
    """Anchor the SHIPPED binary at each frame in `frames` and photograph it there.

    Hit 1 of $4a0 is the boot's own `jmp` arriving, i.e. BEFORE any frame has run, so frame N's
    RESULT is on screen at hit N+1. Hatari counts hits from 1 and rejects an explicit `:1`, which is
    why no anchor here is ever hit 1 — and hit 1 is not a frame anyway.

    Three savebins per anchor, in ONE action file rather than three breakpoints: two breakpoints on
    the same PC and hit count disturb each other's counters, and the measured consequence in the
    sibling project was captures and dumps arriving from different moments. Anchors are told apart
    by the HIT COUNT and share a PC, which is why boot_script's duplicate guard keys on the pair."""
    low, high = SCREEN_REGION
    stops = [(FRAME_LOOP_PC, frame + 1, f"F{frame}.INI", [
        f"savebin {directory / ('OSCR%d.BIN' % frame)} ${low:x} {high - low:#x}",
        f"savebin {directory / ('OFRONT%d.BIN' % frame)} ${wb('SCREEN_FRONT'):x} 4",
        f"savebin {directory / ('OPEN%d.BIN' % frame)} ${SHIFTER_PALETTE:x} {PALETTE_BYTES}",
        f"echo FRAME_{frame}_CAPTURED"]) for frame in frames]
    return boot_script(directory, disk2, extra_stops=stops)


def mode_frames(frames):
    """Photograph the shipped binary at `frames`, for smoke.py's side-by-side."""
    produced, log, status = run_original(lambda d, disk2: frames_script(d, disk2, frames), "frames")
    print(f"-- frames: anchors {frames} at ${FRAME_LOOP_PC:x}, hatari exit={status} "
          f"(full log in {OUT / 'original-frames.log'})")
    faults = machine_faults(log)
    if faults:
        raise SystemExit("FAIL: unhealthy machine: " + " | ".join(faults[:4]))
    BUILD.mkdir(exist_ok=True)
    for frame in frames:
        for stem in ("OSCR", "OFRONT", "OPEN"):
            name = f"{stem}{frame}.BIN"
            if name not in produced:
                raise SystemExit(f"FAIL: the shipped binary produced no {name} — it did not reach "
                                 f"frame {frame}, so there is nothing to compare against")
            (BUILD / name).write_bytes(produced[name])
    print(f"   {len(frames)} frames captured into {BUILD}")
    return True


def frames_argument():
    """`frames` with no argument takes the shim's anchors; `frames N` takes 1..N, which is the form
    that MEASURED those anchors in the first place (see wonderboy_main.c's M2_ANCHOR_FRAMES)."""
    if len(sys.argv) > 2:
        return list(range(1, int(sys.argv[2]) + 1))
    return anchor_frames()


def mode_control(name, fires, disk2):
    """A negative control: remove one injection and require that the anchor is NOT reached."""
    def script(directory, disk2_path):
        return boot_script(directory, disk2_path if disk2 else None, extra_stops=[
            (BOOT_ANCHOR_PC, FIRST_HIT, "ANCHOR.INI", [f"echo {ANCHOR_BEACON}"])])

    _, log, status = run_original(script, name, fires=fires)
    print(f"-- {name} (negative control — the anchor MUST NOT be reached): hatari exit={status} "
          f"(full log in {OUT / ('original-%s.log' % name)})")
    if ANCHOR_BEACON in log:
        raise SystemExit(f"FAIL: the boot reached ${BOOT_ANCHOR_PC:x} with the injection removed, "
                         f"so the injection was not what carried it there and the `dump` mode's "
                         f"claim to be driving the boot is unfounded")
    print(f"OK: without it the boot never reaches ${BOOT_ANCHOR_PC:x} in {RUN_VBLS} vblanks")
    return True


MODES = {
    "dump": mode_dump,
    "neighbour": mode_neighbour,
    "variance": mode_variance,
    "frames": lambda: mode_frames(frames_argument()),
    "nofire": lambda: mode_control("nofire", fires=False, disk2=True),
    "nodisk2": lambda: mode_control("nodisk2", fires=True, disk2=False),
}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if mode not in MODES:
        raise SystemExit(__doc__)
    MODES[mode]()


if __name__ == "__main__":
    main()
