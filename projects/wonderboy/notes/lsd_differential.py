#!/usr/bin/env python3
"""Ground truth for tools/depack_lsd.py: run the ORIGINAL 68000 depack routine and diff.

The routine lives in AUTO/VAPOUR2.PRG's text and is fully PC-relative, so the whole text+data
segment is dropped into a flat image at LOAD_BASE and entered at ENTRY_OFF with a0/a1 set the
way VAPOUR2's caller sets them (a0 = packed file + 4, a1 = destination). The recreate_kit
Musashi oracle (`emu.run`) executes it to its rts; the resulting destination bytes are compared
with the Python depacker's output. Only the oracle is borrowed — Wonder Boy has no
`recreate/project.toml`, so the kit's loader is bound by hand (IMAGE_SIZE is all `emu` needs).

KNOWINGLY UNPINNED: the routine saves $ffff8240.w (palette entry 0), pokes stream bytes into it
as a loading-progress flash, and restores it before rts. That address is outside the oracle's
1 MB image, so shim.c drops every one of those accesses unlogged — reads return 0 and writes go
nowhere, and no counter records them. This harness therefore verifies the DEPACKED BYTES ONLY;
the colour flash is verified nowhere, and exists only as a transcription in lsd_depacker.asm.

Usage: lsd_differential.py [file ...]     (default: every LSD! file under bin/extracted/)
Exit status: 0 all files matched · 1 a file failed, or there was nothing to check
"""
import pathlib
import sys

REVERSE = pathlib.Path(__file__).resolve().parents[3]
TOOLS = REVERSE / "tools"
KIT = TOOLS / "recreate_kit"
ORACLE_LIB = KIT / "oracle" / "build" / "liboracle.so"
# The kit's oracle modules are plain top-level modules under recreate_kit/oracle/; project.load()
# would put that directory on the path, but it needs a project.toml this game does not have.
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(KIT / "oracle"))
import depack_lsd                                                  # noqa: E402
import prg_dis                                                     # noqa: E402
import loader                                                      # noqa: E402

EXTRACTED = pathlib.Path(__file__).resolve().parents[1] / "bin" / "extracted"
VAPOUR2 = EXTRACTED / "AUTO" / "VAPOUR2.PRG"

ENTRY_OFF = 0x7EC            # text offset of the depack routine (see lsd_depacker.asm)

IMAGE_SIZE = 0x100000        # 1 MB flat image
LOAD_BASE = 0x10000          # VAPOUR2's text; clear of the 68000 vector page and of $90.w
PACKED_AT = 0x40000          # the packed file, as if just Fread into a buffer
DEST_AT = 0x80000            # the destination buffer the caller passes in a1
SAVED_A0 = 0x90              # the routine parks its entry a0 in this low-memory long
MAX_INSNS = 50_000_000

# emu derives its stack constants from these at import time; nothing else here uses the loader.
loader.LOAD_BASE = LOAD_BASE
loader.IMAGE_SIZE = IMAGE_SIZE
try:
    import emu                                                     # noqa: E402
except OSError as err:                                             # the ctypes.CDLL at emu import
    sys.exit("cannot load the kit's Musashi oracle %s (%s)\nbuild it first: "
             "make -C projects/joust/recreate oracle" % (ORACLE_LIB, err))

# VAPOUR2's text+data, and the flat image holding it: identical for every file, so build both once
# and copy the image per run. parse_header gives the exact segment bounds — the bytes after them
# are the symbol and relocation tables, which are not part of what the 68000 executes.
_PRG = VAPOUR2.read_bytes()
_HDR = prg_dis.parse_header(_PRG)
TEXT_DATA = _PRG[loader.HEADER:loader.HEADER + _HDR["tlen"] + _HDR["dlen"]]
IMAGE_TEMPLATE = bytearray(IMAGE_SIZE)
IMAGE_TEMPLATE[LOAD_BASE:LOAD_BASE + len(TEXT_DATA)] = TEXT_DATA


def _check_layout(packed_len, unpacked_size):
    """Fail loudly if one region of the flat image would land on top of the next.

    The three regions are placed at fixed addresses, so an oversized input silently corrupting
    the next one is the failure mode that would make a green result meaningless.
    """
    if LOAD_BASE + len(TEXT_DATA) > PACKED_AT:
        raise AssertionError("VAPOUR2's %d bytes of text+data at %#x reach past the packed-file "
                             "buffer at %#x" % (len(TEXT_DATA), LOAD_BASE, PACKED_AT))
    if PACKED_AT + packed_len > DEST_AT:
        raise AssertionError("the %d-byte packed file at %#x reaches past the destination "
                             "buffer at %#x" % (packed_len, PACKED_AT, DEST_AT))
    stack_floor = emu.STACK_TOP - emu.STACK_SCRATCH
    if DEST_AT + unpacked_size > stack_floor:
        raise AssertionError("%d unpacked bytes at %#x reach past the stack scratch floor at %#x"
                             % (unpacked_size, DEST_AT, stack_floor))


def run_original(packed, unpacked_size):
    """Execute the 68000 routine on `packed`; return (destination bytes, write set, insns)."""
    _check_layout(len(packed), unpacked_size)
    image = bytearray(IMAGE_TEMPLATE)
    image[PACKED_AT:PACKED_AT + len(packed)] = packed
    # emu.run rejects a run that hit unmodeled OS behaviour — such a result is fabricated. Its PSG
    # counters stay 0 here: the $ffff8240 flash is off-image but outside the YM2149 block, so
    # shim.c drops it without tallying anything (see this module's docstring).
    mem, writes, out_regs = emu.run(image, LOAD_BASE + ENTRY_OFF,
                                    regs={"a0": PACKED_AT + 4,     # just past the 'LSD!' magic
                                          "a1": DEST_AT},          # destination
                                    max_insns=MAX_INSNS)
    return bytes(mem[DEST_AT:DEST_AT + unpacked_size]), set(writes), out_regs["ninsns"]


def check(path):
    packed = path.read_bytes()
    header = depack_lsd.parse_header(packed)
    unpacked_size = header.unpacked_size
    mine = depack_lsd.depack(packed, header)
    theirs, writes, insns = run_original(packed, unpacked_size)

    stray = {a for a in writes
             if not (DEST_AT <= a < DEST_AT + unpacked_size
                     or a >= emu.STACK_TOP - emu.STACK_SCRATCH
                     or SAVED_A0 <= a < SAVED_A0 + 4)}
    if mine != theirs:
        bad = next(i for i in range(unpacked_size) if mine[i] != theirs[i])
        return "FAIL", "first difference at %#x (mine %02x, 68k %02x)" % (bad, mine[bad], theirs[bad])
    if stray:
        return "FAIL", "%d write(s) outside the destination, e.g. %#x" % (len(stray), min(stray))
    return "ok", "%d -> %d bytes, %d insns" % (len(packed), unpacked_size, insns)


def _is_lsd(path):
    with open(path, "rb") as fh:
        return fh.read(len(depack_lsd.MAGIC)) == depack_lsd.MAGIC


def _label(path):
    """How a file is named in the report: relative to the corpus, or bare if it is outside it."""
    try:
        return str(path.relative_to(EXTRACTED))
    except ValueError:
        return path.name


def main():
    args = sys.argv[1:]
    if args:
        paths = [pathlib.Path(a).resolve() for a in args]
    else:
        paths = sorted(p for p in EXTRACTED.rglob("*") if p.is_file() and _is_lsd(p))
    if not paths:
        # Nothing checked is not a pass: an absent or empty corpus would otherwise report green.
        sys.exit("no LSD! files to check under %s — nothing was verified" % EXTRACTED)
    failures = 0
    for p in paths:
        try:
            verdict, detail = check(p)
        except Exception as e:                                     # noqa: BLE001
            verdict, detail = "FAIL", "%s: %s" % (type(e).__name__, e)
        failures += verdict == "FAIL"
        print("%-4s %-22s %s" % (verdict, _label(p), detail))
    print("\n%d file(s), %d failure(s)" % (len(paths), failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
