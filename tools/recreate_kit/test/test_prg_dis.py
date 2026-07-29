#!/usr/bin/env python3
"""Regression checks for prg_dis's 68000 decoder.

Stdlib only, like ``tools/prg_dis.py`` itself. Runs under the kit's suite
(``cd tools/recreate_kit && make test``) or standalone:

    python3 tools/recreate_kit/test/test_prg_dis.py

The cases are raw 68000 encodings with the length and mnemonic the 68000 Programmer's
Reference requires. Length matters as much as the mnemonic: prg_dis is a *linear sweep*,
so one wrong instruction length desyncs everything after it.
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]          # reverse/tools
sys.path.insert(0, str(TOOLS))
import prg_dis                                       # noqa: E402

GEMDOS_HEADER_LEN = 28  # decode() takes a file offset; image offset 0 lives just past the header
# Extension words a decode may read past the opcode word (movem.l with an abs.l ea reads 8 bytes;
# a reverted fix reads more). Padding with NOPs keeps a wrong decode from raising struct.error, so
# a regression reports a length/mnemonic diff instead of dying inside the reader.
TRAILING_PAD = bytes.fromhex("4e71") * 8

# (encoding, expected length in bytes, expected text)
CASES = [
    # --- MULU/DIVU: the <ea>,Dn forms that hide in the AND (line C) and OR (line 8) groups.
    # These three are verbatim from projects/joust/bin/JOUST.PRG, inside pos_to_screen (entry at
    # ghidra 0x182a2 = image 0x82a2), at ghidra 0x182ae / 0x182ba / 0x182c6 = image 0x82ae /
    # 0x82ba / 0x82c6. (names.txt and Ghidra use image + 0x10000; prg_dis prints image offsets.)
    # The decoder used to print "and.w #$a0,a0" / "or.w #$10,a0" / "and.w #$8,a0" — AND and OR
    # cannot target an address register, so those encodings do not exist.
    ("c0fc00a0", 4, "mulu.w #$a0,d0"),
    ("80fc0010", 4, "divu.w #$10,d0"),
    ("c0fc0008", 4, "mulu.w #$8,d0"),
    # --- MULS/DIVS (opmode 111). The old decoder read opmode 111 as a LONG operand and so
    # consumed 6 bytes for these 4-byte instructions — a sweep desync, not just a bad mnemonic.
    ("c1fc0010", 4, "muls.w #$10,d0"),
    ("81fc0010", 4, "divs.w #$10,d0"),
    ("c7fc0016", 4, "muls.w #$16,d3"),
    # --- non-immediate <ea> operands
    ("c6d1", 2, "mulu.w (a1),d3"),
    ("8aea0004", 4, "divu.w 4(a2),d5"),
    ("ccd8", 2, "mulu.w (a0)+,d6"),
    ("81f900010f2c", 6, "divs.w $10f2c.l,d0"),
    # --- EXG, which hides in AND's "Dn -> <ea>" opmodes (AND cannot target Dn or An either).
    # The first two are verbatim from JOUST at image 0x3a62/0x3a64 = ghidra 0x13a62/0x13a64,
    # where they bracket a bsr.
    ("c141", 2, "exg d0,d1"),
    ("c14b", 2, "exg a0,a3"),
    ("c58d", 2, "exg d2,a5"),
    # --- MOVEP: the other line-0 encoding with an An ea. 4 bytes (a displacement word follows),
    # not the 2-byte dynamic bit op it used to decode as. All four opmodes.
    ("010800ff", 4, "movep.w 255(a0),d0"),
    ("034c0010", 4, "movep.l 16(a4),d1"),
    ("0589fffe", 4, "movep.w d2,-2(a1)"),
    ("07cf0100", 4, "movep.l d3,256(a7)"),
    # --- ...and the dynamic bit ops MOVEP shares line 0 with must decode as before
    ("0110", 2, "btst d0,(a0)"),
    ("01c0", 2, "bset d0,d0"),
    # --- the genuine <ea>,An forms must be untouched
    ("90fc0010", 4, "suba.w #$10,a0"),
    ("b1fc12345678", 6, "cmpa.l #$12345678,a0"),
    ("d1fc12345678", 6, "adda.l #$12345678,a0"),
    ("d0c0", 2, "adda.w d0,a0"),
    # --- and so must the ordinary AND/OR forms next door
    ("c041", 2, "and.w d1,d0"),
    ("c151", 2, "and.w d0,(a1)"),
    ("82bcffff0000", 6, "or.l #$ffff0000,d1"),
    ("8081", 2, "or.l d1,d0"),
]

# --- opcode-space sweep for the "impossible destination" tell ------------------------
OPCODE_WORDS = 1 << 16
REG_FIELD = 8                                              # both register fields are 3 bits
ADDRESS_REGISTERS = tuple("a%d" % n for n in range(REG_FIELD))
# The "Dn -> <ea>" direction of these cannot target an address register, in any line.
AN_DEST_IMPOSSIBLE = ("and", "or", "eor", "add", "sub")

# (line, opmode) pairs whose ea-mode-001 encoding is NOT the instruction prg_dis prints for it.
# Each pair covers 8 (Dx) x 8 (Ay) = 64 opcode words. These are known *mnemonic-only* gaps: ea
# mode 001 takes no extension word, so the 2-byte length prg_dis reports is right and the sweep
# stays in sync — unlike the MULU/MULS/MOVEP bugs, which were length bugs too. Listed here so the
# sweep documents exactly which impossible forms are tolerated, and fails both when a new one
# appears and when one of these is fixed without updating the table.
KNOWN_MNEMONIC_GAPS = {
    (0x8, 4): "SBCD -(Ay),-(Ax)",
    (0x8, 5): "illegal — OR.w Dn,<ea> cannot take An",
    (0x8, 6): "illegal — OR.l Dn,<ea> cannot take An",
    (0x9, 4): "SUBX.B -(Ay),-(Ax)",
    (0x9, 5): "SUBX.W -(Ay),-(Ax)",
    (0x9, 6): "SUBX.L -(Ay),-(Ax)",
    (0xb, 4): "CMPM.b (Ay)+,(Ax)+",
    (0xb, 5): "CMPM.w (Ay)+,(Ax)+",
    (0xb, 6): "CMPM.l (Ay)+,(Ax)+",
    (0xc, 4): "ABCD -(Ay),-(Ax)",
    (0xd, 4): "ADDX.B -(Ay),-(Ax)",
    (0xd, 5): "ADDX.W -(Ay),-(Ax)",
    (0xd, 6): "ADDX.L -(Ay),-(Ax)",
}
# Invisible to this sweep: line C opmode 110 ea mode 000 (0xc180 and friends) is illegal — EXG's
# opmode 10000 does not exist — but prg_dis prints "and.l dX,dY", which is exactly what the legal
# <ea>,Dn direction prints, so no text-level check can separate them. Its length is right, so it
# cannot desync a sweep; it only ever turns up in data.


def decode_one(encoding):
    """Decode `encoding` (hex) as if it sat at image offset 0. Returns (nbytes, text)."""
    image = bytes.fromhex(encoding)
    return prg_dis.decode(b"\x00" * GEMDOS_HEADER_LEN + image + TRAILING_PAD, GEMDOS_HEADER_LEN, 0)


def test_decoder_matches_reference_encodings():
    failures = []
    for encoding, want_len, want_text in CASES:
        got_len, got_text = decode_one(encoding)
        if (got_len, got_text) != (want_len, want_text):
            failures.append("  %-14s got %d bytes %-24r want %d bytes %r"
                            % (encoding, got_len, got_text, want_len, want_text))
    assert not failures, "prg_dis mis-decoded %d encoding(s):\n%s" % (len(failures), "\n".join(failures))


def _sweep_an_destinations():
    """Every opcode word prg_dis decodes to a data-op that writes an address register."""
    found = set()
    for word in range(OPCODE_WORDS):
        _, text = decode_one("%04x" % word)
        mnemonic, _, operands = text.partition(" ")
        if mnemonic.split(".")[0] in AN_DEST_IMPOSSIBLE and operands.endswith(ADDRESS_REGISTERS):
            found.add(word)
    return found


def _allowlisted_words():
    return {(line << 12) | (dx << 9) | (opmode << 6) | (prg_dis.EA_AN << 3) | ay
            for line, opmode in KNOWN_MNEMONIC_GAPS
            for dx in range(REG_FIELD) for ay in range(REG_FIELD)}


def _describe(words, limit=8):
    shown = ["    %04x -> %s" % (w, decode_one("%04x" % w)[1]) for w in sorted(words)[:limit]]
    if len(words) > limit:
        shown.append("    ... and %d more" % (len(words) - limit))
    return "\n".join(shown)


def test_no_impossible_address_register_destination():
    """AND/OR/EOR/ADD/SUB cannot write an address register; emitting one is the mis-decode tell.

    Sweeps the whole opcode space. Checking only the CASES above would be vacuous — they are
    already pinned by exact string equality, so they can never fail here first.
    """
    found = _sweep_an_destinations()
    allowed = _allowlisted_words()
    regressions, allowlist_stale = found - allowed, allowed - found
    message = []
    if regressions:
        message.append("prg_dis decoded %d opcode word(s) to an instruction the 68000 cannot encode:\n%s"
                       % (len(regressions), _describe(regressions)))
    if allowlist_stale:
        message.append("%d opcode word(s) in KNOWN_MNEMONIC_GAPS now decode correctly — drop their "
                       "(line, opmode) entry:\n%s" % (len(allowlist_stale), _describe(allowlist_stale)))
    assert not message, "\n".join(message)


if __name__ == "__main__":
    tests = [test_decoder_matches_reference_encodings, test_no_impossible_address_register_destination]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS %s" % t.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL %s\n%s" % (t.__name__, exc))
        except Exception as exc:  # a reverted fix can over-read the buffer or crash the decoder
            failed += 1
            print("FAIL %s\n  %s: %s" % (t.__name__, type(exc).__name__, exc))
    print("%d/%d passed (%d encodings, %d opcode words swept)"
          % (len(tests) - failed, len(tests), len(CASES), OPCODE_WORDS))
    sys.exit(1 if failed else 0)
