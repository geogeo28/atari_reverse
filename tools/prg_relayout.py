#!/usr/bin/env python3
"""Rewrite a GEMDOS .PRG into the RUN-TIME layout an Alcyon/DRI C small-model crt0 builds.

Stdlib only. Reuses ``tools/prg_dis.py`` for the header and the DRI relocation stream, so
there is exactly one relocation parser on the Python side.

**Why.** TOS loads a .PRG as ``[TEXT][DATA][BSS]``, but the Alcyon/DRI C startup immediately
rearranges it. Bubble Ghost's crt0 (`GHOST_PLAIN.PRG` @ image 0x36) is the textbook case::

    movea.l 24(a5),a0 / movea.l 24(a5),a1 / adda.l 28(a5),a1   ; a0=p_bbase, a1=p_bbase+p_blen
    move.b -(a0),-(a1) ... dbf                                 ; p_dlen bytes: DATA moves UP by p_blen
    movea.l 16(a5),a0 / clr.b (a0)+ ... dbf                    ; p_blen zero bytes from p_dbase
    movea.l 16(a5),a4 / adda.l 28(a5),a4                       ; a4 = p_dbase + p_blen

so the running program is ``[TEXT][BSS][DATA]`` with ``a4`` on the BSS/DATA boundary and every
global addressed ``n(a4)``. A Ghidra image built from the FILE layout therefore has every global
at the wrong address: `var 0x<addr> <name>` has nothing to attach to, and the decompiler prints
`*(a4 + -8560)` noise. Feeding Ghidra the image this tool produces makes
**Ghidra address == run-time address** for TEXT, BSS and DATA alike; pair it with
``ghidra_scripts/SetRegisterValue.java a4 <boundary>`` so the decompiler resolves the `n(a4)`
operands to those addresses.

**What it does.** Every file-layout image offset is mapped through :func:`runtime_offset`
(TEXT unchanged, DATA up by ``blen``, BSS down by ``dlen``), and that map is applied to

  * the image bytes — TEXT, then ``blen`` zero bytes (crt0 clears BSS), then the DATA bytes
    verbatim;
  * each relocation's POSITION — a fixup sitting in DATA moves with its segment;
  * each relocation's TARGET VALUE — a pointer into DATA or BSS is rewritten to the place its
    segment ends up at.

The output header folds BSS into text (``text' = tlen + blen``, ``data' = dlen``, ``bss' = 0``)
so an ordinary PRG loader — `PrgLoader.java` included — lays the whole run-time image down as
one initialised block at the load base.

**A real program fact this exposes.** At true run time a fixup whose target lies in DATA or BSS
is *stale*: TOS relocates it against the FILE layout and this crt0 re-fixes nothing afterwards,
so the pointer keeps aiming at where the segment used to be. Such a program would be broken, and
the DRI small model is built so it cannot happen — the compiler reaches data through ``a4``, not
through absolute pointers (GHOST_PLAIN.PRG's nine fixups are the nine `jmp $xxxx.l` of its jump
table, all targeting TEXT). This tool rewrites those targets to the intended run-time address and
prints a warning naming each one, because an image that quietly reproduces a dangling pointer is
useless to read; if you ever see the warning, check the crt0 for a re-fix pass before trusting it.

**Symbol table.** Carried through byte-for-byte. TEXT- and DATA-section symbol values still land
correctly (a DATA symbol is ``text' + val`` either way), but a BSS-section symbol value is NOT
remapped and will point past DATA; the tool warns when a symbol table is present at all.

**Invariants checked on every run** (a failure raises rather than writing a bad image): the
output re-parsed by ``prg_dis``'s header/reloc parser yields the same fixup count at exactly the
mapped positions, and every original TEXT byte is unchanged except the fixup longwords whose
target was retargeted.

Usage: python3 prg_relayout.py IN.PRG -o OUT.PRG
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prg_dis  # noqa: E402

PRG_MAGIC = 0x601A
HEADER_LEN = prg_dis.HEADER_LEN
HEADER_FMT = ">HIIIIIIH"          # magic, tlen, dlen, blen, slen, res, flags, absflag


def runtime_offset(off, tlen, dlen, blen):
    """Map a FILE-layout image offset to its offset in the [TEXT][BSS][DATA] run-time image."""
    if off < 0 or off >= tlen + dlen + blen:
        raise ValueError("image offset 0x%x outside the program (text+data+bss = 0x%x)"
                         % (off, tlen + dlen + blen))
    if off < tlen:
        return off                       # TEXT does not move
    if off < tlen + dlen:
        return off + blen                # DATA moves up, over the BSS
    return off - dlen                    # BSS moves down, into where DATA was


def encode_reloc_table(fixups):
    """Encode sorted image offsets as a DRI relocation stream (the inverse of parse_reloc)."""
    if not fixups:
        return struct.pack(">I", 0)
    out = bytearray(struct.pack(">I", fixups[0]))
    prev = fixups[0]
    for pos in fixups[1:]:
        delta = pos - prev
        if delta <= 0 or delta % 2:
            raise ValueError("relocation offsets must ascend by an even step, got %d" % delta)
        while delta > prg_dis.RELOC_SKIP_BYTES:
            out.append(prg_dis.RELOC_SKIP)
            delta -= prg_dis.RELOC_SKIP_BYTES
        out.append(delta)
        prev = pos
    out.append(prg_dis.RELOC_END)
    return bytes(out)


def relayout(data, log=print):
    """Return the run-time-layout .PRG built from the file-layout .PRG bytes `data`."""
    head = prg_dis.parse_header(data)
    if head["magic"] != PRG_MAGIC:
        raise ValueError("not a GEMDOS PRG (magic=0x%04x)" % head["magic"])
    tlen, dlen, blen, slen = head["tlen"], head["dlen"], head["blen"], head["slen"]
    if HEADER_LEN + tlen + dlen + slen > len(data):
        raise ValueError("header lengths overrun the file (%d bytes)" % len(data))
    if slen:
        log("WARNING: %d bytes of DRI symbols carried through unchanged; BSS-section symbol "
            "values are NOT remapped and will point past DATA" % slen)

    image = data[HEADER_LEN:HEADER_LEN + tlen + dlen]
    symbols = data[HEADER_LEN + tlen + dlen:HEADER_LEN + tlen + dlen + slen]
    out_image = bytearray(image[:tlen] + b"\0" * blen + image[tlen:])

    if head["absf"]:
        log("relocations: none (ABSFLAG=0x%x set in the header)" % head["absf"])
        fixups = []
    else:
        fixups = sorted(prg_dis.parse_reloc(data, head))
    moved_targets = []
    for pos in fixups:
        new_pos = runtime_offset(pos, tlen, dlen, blen)
        target = struct.unpack_from(">I", image, pos)[0]
        new_target = runtime_offset(target, tlen, dlen, blen)
        if new_target != target:
            moved_targets.append((pos, target, new_target))
        struct.pack_into(">I", out_image, new_pos, new_target)
    for pos, target, new_target in moved_targets:
        log("WARNING: fixup at image 0x%x points at 0x%x (DATA/BSS); retargeted to 0x%x. At real "
            "run time this pointer is STALE — TOS relocates it against the file layout and the "
            "crt0 data move re-fixes nothing." % (pos, target, new_target))

    new_fixups = [runtime_offset(p, tlen, dlen, blen) for p in fixups]
    out = bytearray(struct.pack(HEADER_FMT, PRG_MAGIC, tlen + blen, dlen, 0, slen,
                                0, head["flags"], head["absf"]))
    out += out_image + symbols + encode_reloc_table(sorted(new_fixups))
    _check_invariants(bytes(out), image, tlen, blen, new_fixups, moved_targets)
    log("relayout: text 0x%x + bss 0x%x -> text 0x%x, data 0x%x, %d relocations (%d retargeted)"
        % (tlen, blen, tlen + blen, dlen, len(fixups), len(moved_targets)))
    return bytes(out)


def _check_invariants(out, image, tlen, blen, new_fixups, moved_targets):
    head = prg_dis.parse_header(out)
    got = sorted(prg_dis.parse_reloc(out, head))
    if got != sorted(new_fixups):
        raise AssertionError("re-parsed relocations differ from the mapped ones: %r vs %r"
                             % (got, sorted(new_fixups)))
    out_text = out[HEADER_LEN:HEADER_LEN + tlen]
    retargeted = {pos + i for pos, _old, _new in moved_targets for i in range(4)}
    for pos in range(tlen):
        if out_text[pos] != image[pos] and pos not in retargeted:
            raise AssertionError("TEXT byte at image 0x%x changed" % pos)
    if any(out[HEADER_LEN + tlen:HEADER_LEN + tlen + blen]):
        raise AssertionError("the BSS gap is not zero-filled")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("prg", help="the file-layout GEMDOS .PRG")
    ap.add_argument("-o", "--out", required=True, help="where to write the run-time-layout .PRG")
    args = ap.parse_args()
    data = Path(args.prg).read_bytes()
    Path(args.out).write_bytes(relayout(data))
    print("wrote %s" % args.out)


if __name__ == "__main__":
    main()
