#!/usr/bin/env python3
"""Ground truth for tools/depack_rad.py: run the ORIGINAL 68000 depack routine and diff.

The routine lives in the game's own AUTO/SWB.PRG. SWB.PRG's text is NOT position-independent:
its entry stub (text $213e0) does a Super(), copies text $8.. down to absolute $400 and jumps
there, so every absolute reference in the body — including this routine's own scratch long —
assumes that address map. `recreate/project.toml` is bound to exactly that map: its
`load_base = 0x3f8` is chosen so that `load_base + 8 == 0x400`, which makes the loaded image
BE the runtime image and the stub's copy an identity copy. So this harness loads the .PRG
through `recreate_kit.project.load()` like every other differential in the workspace, and
proves the three things that equality rests on rather than assuming them (see
`_load_runtime_image`): the stub still is the copy loop this was written against, the base
still satisfies `load_base + COPY_SRC_OFF == RUN_BASE`, and no relocation fixup lands inside
the copied body.

It then enters the routine at RUN_BASE-relative ENTRY with a0/a1 set the way the game's five
call sites set them (a0 = the file as read off disk, a1 = destination). The recreate_kit
Musashi oracle (`emu.run`) executes it to its rts; the resulting destination bytes are compared
with the Python depacker's output.

The routine touches no hardware at all: no palette, no PSG, no disk. Its whole observable
effect is the destination buffer plus one scratch long, and both are inside the oracle's image,
so unlike the LSD! harness there is no off-image side effect hiding from the diff.

KNOWINGLY UNPINNED, even so:
  * depack_rad's CHECKSUM GATE is not pinned by this corpus, and the damaged section below does
    NOT reach it. The 68000 gets there on all four damaged overlays — they come back with its
    defined failure status — but depack_rad refuses each of them EARLIER, at a host-only guard
    the 68000 does not have (DAMAGED_GUARDS records which, per file, and asserts it). Deleting
    `if stream.checksum:` from depack_rad leaves this differential green. That gate is pinned
    only synthetically, by test_bad_checksum_is_refused in
    tools/recreate_kit/test/test_depack_rad.py, which corrupts the checksum of an otherwise
    well-formed stream; no file on either disk reaches it.
  * The four overlays that the protection left holes in are read from bin/disk2_repaired/, a
    REPAIRED HYBRID (authentic dump bytes outside the holes, crack bytes inside them — see
    commit 17f9bf2 and notes/crack_differential.py). A green row for one of those four proves
    the two implementations agree on those bytes; it does NOT prove the bytes are what the
    pressed disk held. No format claim in the notes rests on those four files alone.
  * d0 on the SUCCESS path is whatever the spent bit buffer left behind — the game's callers
    ignore it, and so does this harness. Only the failure path's d0 is a defined value, and
    that is what the damaged-file section below checks.
  * Timing: the failure path spins a 65536-iteration delay loop before returning. The oracle
    counts its instructions but nothing here asserts on them.

Usage: rad_differential.py [file ...]     (default: the whole .RAD corpus under bin/)
Exit status: 0 all files matched · 1 a file failed, or there was nothing to check
"""
import pathlib
import sys

REVERSE = pathlib.Path(__file__).resolve().parents[3]
TOOLS = REVERSE / "tools"
RECREATE = pathlib.Path(__file__).resolve().parents[1] / "recreate"
ORACLE_LIB = TOOLS / "recreate_kit" / "oracle" / "build" / "liboracle.so"
sys.path.insert(0, str(TOOLS))
import depack_rad                                                 # noqa: E402
import prg_dis                                                    # noqa: E402
from recreate_kit import project                                  # noqa: E402

# Binds loader.LOAD_BASE / loader.IMAGE_SIZE from recreate/project.toml, which is the whole
# reason this game's base is 0x3f8. Must happen before `emu` is imported: emu derives its stack
# constants from loader.IMAGE_SIZE at import time.
CONFIG = project.load(RECREATE)
import loader                                                     # noqa: E402
try:
    import emu                                                    # noqa: E402
except OSError as err:                                            # the ctypes.CDLL at emu import
    sys.exit("cannot load the kit's Musashi oracle %s (%s)\nbuild it first: "
             "make -C projects/joust/recreate oracle" % (ORACLE_LIB, err))

BIN = pathlib.Path(__file__).resolve().parents[1] / "bin"
# disk1 is clean. disk2/ is the authentic dump and still carries the protection's holes in four
# overlays, so the decodable corpus takes those four — and, so the corpus is one consistent set,
# all of disk 2 — from the repaired extraction. The damaged originals get their own check below.
CLEAN_DIR = "disk1"
REPAIRED_DIR = "disk2_repaired"
CORPUS_DIRS = (CLEAN_DIR, REPAIRED_DIR)
DAMAGED_DIR = "disk2"
RAD_SUFFIX = ".RAD"

# --- how SWB.PRG's entry stub lays the game out in memory (text $213e0) ----------------------
RUN_BASE = 0x400             # `lea $400.l,a1`   — where the body is copied to and jumped to
COPY_SRC_OFF = 8             # `lea $8.l,a0`     — text offset the copy starts from
COPY_BYTES = 0x84F6 * 4      # `move.l #$84f6,d0`— the loop moves that many LONGWORDS
# The copy loop and the jump that follows it, verbatim (the ON-DISK bytes, before relocation).
# Asserted so that a different build of SWB.PRG cannot quietly be laid out under this harness at
# the wrong base.
STUB_OFF = 0x213F0
STUB_BYTES = bytes.fromhex("43f900000400"      # lea    $400.l,a1
                           "41f900000008"      # lea    $8.l,a0
                           "203c000084f6"      # move.l #$84f6,d0
                           "22d8"              # move.l (a0)+,(a1)+
                           "5380"              # subq.l #1,d0
                           "6600fffa"          # bne.w  the move
                           "4ef900000400")     # jmp    $400.l

# --- the routine, in the address map that copy produces --------------------------------------
DEPACK_TEXT_OFF = 0x596A                                     # see notes/rad_depacker.asm
ENTRY = RUN_BASE + DEPACK_TEXT_OFF - COPY_SRC_OFF            # = $5d62
SAVED_A7 = RUN_BASE + 0x5A42 - COPY_SRC_OFF                  # = $5e3a, the routine's scratch long
SAVED_A7_LEN = 4
# `moveq #$ff,d0` SIGN-EXTENDS: the failure status is the full longword, not $ff. Compared whole,
# so a success-path d0 that merely ends in $ff cannot pass for it.
FAIL_STATUS = 0xFFFFFFFF

PACKED_AT = 0x40000          # the packed file, as if just read off disk into a buffer
DEST_AT = 0x80000            # the destination buffer the caller passes in a1
# The destination is pre-filled with this rather than left zeroed, because the Python depacker
# decodes into a zeroed bytearray: a match with offset 0 sources the byte it is about to write,
# which is 0 in Python and whatever the buffer last held on the machine (the game's five call
# sites reuse fixed load buffers). No corpus stream does that today — 0 of 27,166 matches — and a
# zeroed destination here would make the two agree by accident if one ever did.
DEST_POISON = 0x5A
MAX_INSNS = 50_000_000

# What the PYTHON side refuses each damaged file with. Naming the expected guard per file is what
# makes the damaged section a pin rather than a coincidence: without it, the two implementations
# could refuse for entirely unrelated reasons and this harness would still print "ok". A file not
# in this table fails loudly — read which guard fires, and why, before adding it. Keyed by path
# relative to DAMAGED_DIR (a bare name today; disk 1 already keeps files in a subdirectory).
DAMAGED_GUARDS = {
    "OVALAY4B.RAD": depack_rad.GUARD_MATCH_PAST_END,
    "OVALAY5B.RAD": depack_rad.GUARD_MATCH_PAST_END,
    "OVALAY6A.RAD": depack_rad.GUARD_STREAM_UNDERRUN,
    "OVALAY9A.RAD": depack_rad.GUARD_STREAM_UNDERRUN,
}


def _load_runtime_image():
    """SWB.PRG loaded at project.toml's base, which IS its runtime map — proven, not assumed.

    Three claims make `load_base = 0x3f8` equal to running the entry stub's copy; each is checked
    here, because a silently false one would put the routine at an address it was never copied to
    and every row below would be diffing the wrong bytes.
    """
    if CONFIG.load_base + COPY_SRC_OFF != RUN_BASE:
        raise AssertionError("project.toml's load_base %#x + the stub's copy source offset %#x is "
                             "%#x, not the runtime base %#x — loading is no longer the same as "
                             "running" % (CONFIG.load_base, COPY_SRC_OFF,
                                          CONFIG.load_base + COPY_SRC_OFF, RUN_BASE))
    prg = CONFIG.prg.read_bytes()
    header = prg_dis.parse_header(prg)
    text = prg[loader.HEADER:loader.HEADER + header["tlen"]]
    if text[STUB_OFF:STUB_OFF + len(STUB_BYTES)] != STUB_BYTES:
        raise AssertionError("SWB.PRG's entry stub at text %#x is not the copy-to-$%x loop this "
                             "harness was written against — the address map below is unproven"
                             % (STUB_OFF, RUN_BASE))
    # A fixup inside the copied body would make the loaded bytes differ from the bytes the stub
    # would have copied, so the identity-copy claim only holds while every fixup is outside it.
    body = range(RUN_BASE, RUN_BASE + COPY_BYTES)
    inside = sorted(CONFIG.load_base + off for off in prg_dis.parse_reloc(prg, header)
                    if CONFIG.load_base + off in body or CONFIG.load_base + off + 3 in body)
    if inside:
        raise AssertionError("%d relocation fixup(s) land inside the copied body [%#x, %#x), e.g. "
                             "%#x — the loaded image is no longer the bytes the entry stub copies"
                             % (len(inside), RUN_BASE, RUN_BASE + COPY_BYTES, inside[0]))
    return loader.load_image(CONFIG.prg)


IMAGE_TEMPLATE = _load_runtime_image()


def _check_layout(packed_len, unpacked_size):
    """Fail loudly if one region of the flat image would land on top of the next.

    The three regions are placed at fixed addresses, so an oversized input silently corrupting
    the next one is the failure mode that would make a green result meaningless.
    """
    if loader.PROGRAM_END > PACKED_AT:
        raise AssertionError("SWB.PRG reaches %#x, past the packed-file buffer at %#x"
                             % (loader.PROGRAM_END, PACKED_AT))
    if PACKED_AT + packed_len > DEST_AT:
        raise AssertionError("the %d-byte packed file at %#x reaches past the destination buffer "
                             "at %#x" % (packed_len, PACKED_AT, DEST_AT))
    stack_floor = emu.STACK_TOP - emu.STACK_SCRATCH
    if DEST_AT + unpacked_size > stack_floor:
        raise AssertionError("%d unpacked bytes at %#x reach past the stack scratch floor at %#x"
                             % (unpacked_size, DEST_AT, stack_floor))


def run_original(packed, unpacked_size):
    """Execute the 68000 routine on `packed`; return (destination bytes, write set, out_regs)."""
    _check_layout(len(packed), unpacked_size)
    image = bytearray(IMAGE_TEMPLATE)
    image[PACKED_AT:PACKED_AT + len(packed)] = packed
    image[DEST_AT:DEST_AT + unpacked_size] = bytes([DEST_POISON]) * unpacked_size
    # emu.run rejects a run that hit unmodeled OS behaviour — such a result is fabricated.
    mem, writes, out_regs = emu.run(image, ENTRY,
                                    regs={"a0": PACKED_AT,        # the file, header included
                                          "a1": DEST_AT},         # destination
                                    max_insns=MAX_INSNS)
    return bytes(mem[DEST_AT:DEST_AT + unpacked_size]), set(writes), out_regs


def _stray_write_failure(writes, unpacked_size):
    """A complaint about writes the routine is not entitled to make — anything but the
    destination, the stack and the one scratch long it parks a7 in — or None if there are none."""
    stray = {a for a in writes
             if not (DEST_AT <= a < DEST_AT + unpacked_size
                     or a >= emu.STACK_TOP - emu.STACK_SCRATCH
                     or SAVED_A7 <= a < SAVED_A7 + SAVED_A7_LEN)}
    if not stray:
        return None
    return "%d write(s) outside the destination, e.g. %#x" % (len(stray), min(stray))


def check(path):
    """A file both implementations must decode, to the same bytes."""
    packed = path.read_bytes()
    header = depack_rad.parse_header(packed)
    unpacked_size = header.unpacked_size
    mine = depack_rad.depack(packed, header)
    theirs, writes, out_regs = run_original(packed, unpacked_size)

    if mine != theirs:
        bad = next(i for i in range(unpacked_size) if mine[i] != theirs[i])
        return "FAIL", "first difference at %#x (mine %02x, 68k %02x)" % (bad, mine[bad], theirs[bad])
    stray = _stray_write_failure(writes, unpacked_size)
    if stray:
        return "FAIL", stray
    return "ok", "%d -> %d bytes, %d insns" % (len(packed), unpacked_size, out_regs["ninsns"])


def check_damaged(path):
    """A file both implementations must REJECT — each for the reason recorded for it.

    These four overlays are the disk's own damaged copies, and they are the only files in the
    corpus that reach the 68000's single failure branch (`tst.l d5 / bne`), so they are what pins
    its defined failure status. They do NOT reach depack_rad's matching checksum gate: the Python
    side refuses earlier, at a host-only guard, and DAMAGED_GUARDS says which. See this module's
    KNOWINGLY UNPINNED note — what is proven here is "both refuse, for these two known reasons",
    not "both refuse on the checksum".
    """
    expected_guard = DAMAGED_GUARDS.get(_damaged_key(path))
    if expected_guard is None:
        return "FAIL", ("no expected refusal recorded for this file — read which depack_rad guard "
                        "refuses it, and why, then add it to DAMAGED_GUARDS")
    packed = path.read_bytes()
    try:
        header = depack_rad.parse_header(packed)
    except depack_rad.DepackError as err:
        # Damage inside the 12-byte header itself, which is a different case: there is no
        # unpacked length to lay the destination out from, so this harness cannot set the run up
        # at all. Say that, rather than let a bare exception read as "the decoders disagree".
        return "FAIL", "cannot diff a file whose own header is damaged (%s)" % err
    try:
        depack_rad.depack(packed, header)
        return "FAIL", "depack_rad accepted a file the 68000 routine rejects"
    except depack_rad.DepackError as err:
        if err.guard != expected_guard:
            return "FAIL", ("depack_rad refused it at the %r guard, not at the recorded %r"
                            % (err.guard, expected_guard))
    _, writes, out_regs = run_original(packed, header.unpacked_size)
    if out_regs["d0"] != FAIL_STATUS:
        return "FAIL", ("the 68000 returned d0=%#010x, not the failure status %#010x"
                        % (out_regs["d0"], FAIL_STATUS))
    stray = _stray_write_failure(writes, header.unpacked_size)
    if stray:
        return "FAIL", stray
    return "ok", "68k checksum (d0=%#010x, %d insns) · depack_rad %r" % (out_regs["d0"],
                                                                        out_regs["ninsns"],
                                                                        expected_guard)


def _label(path):
    """How a file is named in the report: relative to bin/, so the corpus it came from shows."""
    try:
        return str(path.relative_to(BIN))
    except ValueError:
        return path.name


def _corpus():
    return sorted(p for d in CORPUS_DIRS for p in (BIN / d).rglob("*" + RAD_SUFFIX) if p.is_file())


def _damaged_key(path):
    """A damaged file's key in DAMAGED_GUARDS: its path relative to DAMAGED_DIR."""
    return str(path.relative_to(BIN / DAMAGED_DIR))


def _damaged():
    """The disk2/ originals that differ from their repaired counterparts.

    Paired by path RELATIVE to the corpus root, not by bare filename: disk1 already keeps files
    in an AUTO/ subdirectory, so a flat pairing would silently drop any file a future mirrored
    layout puts in one.
    """
    damaged_root, repaired_root = BIN / DAMAGED_DIR, BIN / REPAIRED_DIR
    pairs = ((p, repaired_root / p.relative_to(damaged_root))
             for p in damaged_root.rglob("*" + RAD_SUFFIX) if p.is_file())
    return sorted(p for p, repaired in pairs
                  if repaired.exists() and p.read_bytes() != repaired.read_bytes())


def _report(title, paths, checker):
    print("--- %s" % title)
    failures = 0
    for p in paths:
        try:
            verdict, detail = checker(p)
        except Exception as e:                                    # noqa: BLE001
            verdict, detail = "FAIL", "%s: %s" % (type(e).__name__, e)
        failures += verdict == "FAIL"
        print("%-4s %-30s %s" % (verdict, _label(p), detail))
    print("%d file(s), %d failure(s)\n" % (len(paths), failures))
    return failures


def main():
    args = sys.argv[1:]
    if args:
        paths = [pathlib.Path(a).resolve() for a in args]
        sys.exit(1 if _report("named files", paths, check) else 0)

    intact, damaged = _corpus(), _damaged()
    # Nothing checked is not a pass: an absent or empty corpus would otherwise report green. The
    # damaged set is required too — without it the 68000's failure branch is verified nowhere.
    if not intact:
        sys.exit("no %s files under %s — nothing was verified"
                 % (RAD_SUFFIX, ", ".join(str(BIN / d) for d in CORPUS_DIRS)))
    missing = sorted(set(DAMAGED_GUARDS) - {_damaged_key(p) for p in damaged})
    if missing:
        sys.exit("%d damaged %s file(s) under %s are gone (%s) — the 68000's failure branch would "
                 "be verified on fewer files than this harness records"
                 % (len(missing), RAD_SUFFIX, BIN / DAMAGED_DIR, ", ".join(missing)))
    failures = _report("intact streams: both implementations decode, byte for byte", intact, check)
    failures += _report("damaged streams (the dump's own holes): both implementations refuse",
                        damaged, check_damaged)
    print("%d file(s) total, %d failure(s)" % (len(intact) + len(damaged), failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
