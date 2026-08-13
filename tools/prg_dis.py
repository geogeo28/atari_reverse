#!/usr/bin/env python3
"""Reloc-aware GEMDOS .PRG analyzer + first-pass 68000 linear-sweep disassembler.

Stdlib only. Priority is *correct instruction length* (via 68000 effective-address
extension-word rules) so the linear sweep does not desync; mnemonic fidelity is
"good enough for a first pass" — refine in Ghidra. Traps are auto-named, and
longwords listed in the relocation table are flagged (they are absolute pointers,
i.e. future labels).

Usage: python3 prg_dis.py FILE.PRG [--data] [--start OFF] [--len N] [--base ADDR]

`--base` sets the address the image is loaded at, so printed addresses (and
pc-relative targets) are RUNTIME addresses instead of image offsets. It matters for
position-DEPENDENT programs that relocate themselves to a fixed address and then use
absolute operands — a listing at the default base 0 is off by the load base on every
line and silently mismatches the project's names.txt. See docs/m68k-disassembly.md.
"""
import struct
import sys

# --- GEMDOS (trap #1) / BIOS (#13) / XBIOS (#14) function names -----------------
GEMDOS = {
    0x00: "Pterm0", 0x01: "Cconin", 0x02: "Cconout", 0x09: "Cconws", 0x0A: "Cconrs",
    0x10: "Cconos", 0x20: "Super", 0x2F: "Fgetdta", 0x30: "Sversion", 0x39: "Dcreate",
    0x3A: "Ddelete", 0x3B: "Dsetpath", 0x3C: "Fcreate", 0x3D: "Fopen", 0x3E: "Fclose",
    0x3F: "Fread", 0x40: "Fwrite", 0x41: "Fdelete", 0x42: "Fseek", 0x43: "Fattrib",
    0x47: "Dgetpath", 0x48: "Malloc", 0x49: "Mfree", 0x4A: "Mshrink", 0x4B: "Pexec",
    0x4C: "Pterm", 0x4E: "Fsfirst", 0x4F: "Fsnext", 0x56: "Frename",
}
BIOS = {0x00: "Getmpb", 0x01: "Bconstat", 0x02: "Bconin", 0x03: "Bconout",
        0x04: "Rwabs", 0x05: "Setexc", 0x06: "Tickcal", 0x07: "Getbpb",
        0x08: "Bcostat", 0x09: "Mediach", 0x0A: "Drvmap", 0x0B: "Kbshift"}
# Key = the XBIOS opcode NUMBER. TOS references print these in DECIMAL (Dosound 32, Vsync 37,
# Supexec 38) — convert before writing the key here. The original table pasted several decimal
# numbers straight in as hex literals (0x20 "Supexec", when 0x20 = 32 = Dosound), which mislabelled
# Joust's whole sound layer until the body reads caught it — see docs/tos-os-calls.md's warning.
# Hand-mirrored in AtariOsTrapAnnotate.java; change both together.
XBIOS = {0x00: "Initmous", 0x02: "Physbase", 0x03: "Logbase", 0x04: "Getrez",
         0x05: "Setscreen", 0x06: "Setpalette", 0x07: "Setcolor", 0x08: "Floprd",
         0x09: "Flopwr", 0x0E: "Iorec", 0x0F: "Rsconf", 0x11: "Random",
         0x14: "Scrdmp", 0x18: "Bioskeys", 0x19: "Ikbdws", 0x1C: "Giaccess",
         0x1F: "Xbtimer", 0x20: "Dosound", 0x21: "Setprt", 0x22: "Kbdvbase",
         0x25: "Vsync", 0x26: "Supexec", 0x27: "Puntaes"}
TRAPVEC = {1: ("GEMDOS", GEMDOS), 13: ("BIOS", BIOS), 14: ("XBIOS", XBIOS)}


def rd16(d, p): return struct.unpack(">H", d[p:p + 2])[0]
def rd32(d, p): return struct.unpack(">I", d[p:p + 4])[0]
def s16(x): return x - 0x10000 if x & 0x8000 else x
def s8(x): return x - 0x100 if x & 0x80 else x


def parse_header(d):
    magic, tlen, dlen, blen, slen, res, flags, absf = struct.unpack(">HIIIIIIH", d[:28])
    return dict(magic=magic, tlen=tlen, dlen=dlen, blen=blen, slen=slen,
                flags=flags, absf=absf, sym_off=28 + tlen + dlen,
                reloc_off=28 + tlen + dlen + slen)


# DRI relocation stream: after the first fixup offset (a longword), one byte per step.
# RELOC_SKIP is the trap — it advances the cursor and fixes up NOTHING, and a parser that adds a
# fixup for it corrupts one longword every RELOC_SKIP_BYTES. That bug shipped in
# tools/ghidra_scripts/PrgLoader.java and silently corrupted every project's Ghidra DB; see
# docs/binary-formats.md. This function is the canonical implementation the Java one mirrors, and
# tools/recreate_kit/test/test_reloc_table.py pins the two together.
RELOC_END = 0
RELOC_SKIP = 1
RELOC_SKIP_BYTES = 254


def parse_reloc(d, h):
    """Return set of image offsets (relative to text base = 0) needing relocation."""
    off = h["reloc_off"]
    if off >= len(d):
        return set()
    first = rd32(d, off)
    off += 4
    if first == 0:
        return set()
    fixes = {first}
    cur = first
    while off < len(d):
        b = d[off]; off += 1
        if b == RELOC_END:
            break
        if b == RELOC_SKIP:
            cur += RELOC_SKIP_BYTES          # a gap wider than a byte, NOT a fixup
        else:
            cur += b
            fixes.add(cur)
    return fixes


# --- effective-address decoding: returns (text, extra_bytes_consumed) -----------
EA_AN = 1  # ea mode field 001 = "An direct"; illegal for many ops, which makes it a decode tell


def ea(d, p, mode, reg, size, pc_after_op):
    if mode == 0: return "d%d" % reg, 0
    if mode == 1: return "a%d" % reg, 0
    if mode == 2: return "(a%d)" % reg, 0
    if mode == 3: return "(a%d)+" % reg, 0
    if mode == 4: return "-(a%d)" % reg, 0
    if mode == 5: return "%d(a%d)" % (s16(rd16(d, p)), reg), 2
    if mode == 6:
        ext = rd16(d, p)
        return "idx(a%d)" % reg, 2
    if mode == 7:
        if reg == 0: return "$%x.w" % rd16(d, p), 2
        if reg == 1: return "$%x.l" % rd32(d, p), 4
        if reg == 2:
            disp = s16(rd16(d, p))
            return "$%x(pc)" % ((pc_after_op + disp) & 0xffffff), 2
        if reg == 3:
            rd16(d, p)
            return "idx(pc)", 2
        if reg == 4:
            if size == 2: return "#$%x" % rd32(d, p), 4
            return "#$%x" % (rd16(d, p) & (0xff if size == 0 else 0xffff)), 2
    return "?", 0


SZC = {0: ".b", 1: ".w", 2: ".l"}
# In lines 9/B/D, opmode 011/111 is the "<ea> -> An, word/long" form (SUBA/CMPA/ADDA).
# Lines 8 and C have no such form — the 68000 cannot OR/AND into an address register — so
# there those two opmodes are the word-size divide/multiply, "<ea> -> Dn" with a .w source.
# Any decoder printing "and.w #imm,a0" is emitting an instruction that does not exist.
MULDIV = {(8, 3): "divu", (8, 7): "divs", (0xc, 3): "mulu", (0xc, 7): "muls"}
# Same tell in line C's "Dn -> <ea>" opmodes: AND cannot target Dn or An either, so
# (line, opmode, ea-mode) triples that would decode as one of those are really EXG.
EXG_FORMS = {(0xc, 5, 0): "exg d%d,d%d", (0xc, 5, 1): "exg a%d,a%d", (0xc, 6, 1): "exg d%d,a%d"}
# ...and BELOW the EXG opmodes sits a whole FAMILY of two-register instructions that the
# "Dn -> <ea>" reading gets wrong: opmodes 100/101/110 with ea mode 000 (a register pair) or 001 (a
# memory pair) are ABCD/SBCD, ADDX/SUBX and CMPM. All are two bytes, exactly as the wrong reading
# is, so the sweep never desyncs -- these are mnemonic and OPERAND-ORDER bugs only.
#
# THE OPERAND ORDER IS THE HALF WITH NO TELL. Rx is bits 11-9 and Ry bits 2-0, and every one of
# these is written `<Ry>,<Rx>` with **Rx the DESTINATION** -- so `d101` is `addx.b d1,d0` (d0 += d1
# + X) where the old reading printed `add.b d0,d1` and named the wrong register as the target. The
# -(An) forms at least LOOK impossible (`and.b d1,a0` writes an address register, which the sweep in
# tools/recreate_kit/test/test_prg_dis.py catches); the REGISTER forms print as a perfectly ordinary
# `add.b d0,d1` and no automatic check can see them, which is why the reference encodings in that
# test pin the order explicitly. Missing the ABCD half cost two wrong routine NAMES in
# projects/wonderboy/names.txt ($51ac's `abcd d1,d0` read as a mask) before the bytes were re-read.
PAIR_OPS = {0x8: "sbcd", 0x9: "subx", 0xb: "cmpm", 0xc: "abcd", 0xd: "addx"}
PAIR_BYTE_ONLY = (0x8, 0xc)      # SBCD/ABCD have no .w/.l: those opmodes are EXG (C) or illegal (8)
PAIR_EA_REGISTER, PAIR_EA_MEMORY = 0, 1


def pair_op(top, opmode, m, rx, ry):
    """ABCD/SBCD/ADDX/SUBX/CMPM, or None when (line, opmode, ea mode) is not one of them."""
    mn = PAIR_OPS.get(top)
    if mn is None or not 4 <= opmode <= 6 or m not in (PAIR_EA_REGISTER, PAIR_EA_MEMORY):
        return None
    if top in PAIR_BYTE_ONLY and opmode != 4:
        return None
    # CMPM has ONLY the postincrement form; line B's register encoding is an ordinary EOR.x Dn,Dn.
    if top == 0xb:
        return None if m != PAIR_EA_MEMORY else "cmpm%s (a%d)+,(a%d)+" % (SZC[opmode - 4], ry, rx)
    # The decimal pair are byte-only and are conventionally written with no size suffix at all.
    size = "" if top in PAIR_BYTE_ONLY else SZC[opmode - 4]
    if m == PAIR_EA_REGISTER:
        return "%s%s d%d,d%d" % (mn, size, ry, rx)
    return "%s%s -(a%d),-(a%d)" % (mn, size, ry, rx)
# Branch form: cc 0/1 = BRA/BSR. Scc/DBcc form: cc 0/1 = T/F (so DBcc 1 = DBRA).
CC = ["ra", "sr", "hi", "ls", "cc", "cs", "ne", "eq",
      "vc", "vs", "pl", "mi", "ge", "lt", "gt", "le"]
CC2 = ["t", "f", "hi", "ls", "cc", "cs", "ne", "eq",
       "vc", "vs", "pl", "mi", "ge", "lt", "gt", "le"]


def decode(d, p, base):
    """Decode one instruction at file offset p. Return (nbytes, text)."""
    w = rd16(d, p)
    pc2 = base + (p - 28) + 2  # image address just past opcode word (for pc-relative)
    top = w >> 12

    def two_ea(size, moff, mode, r):  # helper: render ea and add its length
        t, c = ea(d, p + 2, mode, r, size, pc2)
        return t, c

    # ---- MOVE / MOVEA ----
    if top in (1, 2, 3):
        size = {1: 0, 3: 1, 2: 2}[top]
        sm, sr = (w >> 3) & 7, w & 7
        dm, dr = (w >> 6) & 7, (w >> 9) & 7
        st, sc = ea(d, p + 2, sm, sr, size, pc2)
        dt, dc = ea(d, p + 2 + sc, dm, dr, size, pc2 + sc)
        mn = "movea" if dm == 1 else "move"
        return 2 + sc + dc, "%s%s %s,%s" % (mn, SZC[size], st, dt)

    # ---- MOVEQ ----
    if top == 7 and not (w & 0x0100):
        return 2, "moveq #$%x,d%d" % (w & 0xff, (w >> 9) & 7)

    # ---- Bcc / BRA / BSR ----
    if top == 6:
        cc, disp = (w >> 8) & 0xf, w & 0xff
        mn = "b" + CC[cc]
        if disp == 0:
            tgt = (pc2 + s16(rd16(d, p + 2))) & 0xffffff
            return 4, "%s.w $%x" % (mn, tgt)
        if disp == 0xff:
            tgt = (pc2 + struct.unpack(">i", d[p + 2:p + 6])[0]) & 0xffffff
            return 6, "%s.l $%x" % (mn, tgt)
        return 2, "%s.s $%x" % (mn, (pc2 + s8(disp)) & 0xffffff)

    # ---- line 0: immediate + bit ops ----
    if top == 0:
        imm_ops = {0x00: "ori", 0x02: "andi", 0x04: "subi",
                   0x06: "addi", 0x0a: "eori", 0x0c: "cmpi"}
        hi = (w >> 8) & 0xff
        if hi in imm_ops:
            size = (w >> 6) & 3
            m, r = (w >> 3) & 7, w & 7
            if size == 2:
                imm, ic = rd32(d, p + 2), 4
            else:
                imm, ic = rd16(d, p + 2), 2
            t, c = ea(d, p + 2 + ic, m, r, size, pc2 + ic)
            return 2 + ic + c, "%s%s #$%x,%s" % (imm_ops[hi], SZC.get(size, "?"), imm, t)
        if hi == 0x08:  # static bit op: BTST/BCHG/BCLR/BSET #n
            bit = ((w >> 6) & 3)
            names = ["btst", "bchg", "bclr", "bset"]
            m, r = (w >> 3) & 7, w & 7
            n = rd16(d, p + 2)
            t, c = ea(d, p + 4, m, r, 0, pc2 + 2)
            return 4 + c, "%s #%d,%s" % (names[bit], n & 0xff, t)
        if (w & 0x0100):  # dynamic bit op with Dn -- or MOVEP, which shares this half of line 0
            opmode = (w >> 6) & 3
            m, r = (w >> 3) & 7, w & 7
            dn = (w >> 9) & 7
            if m == EA_AN:
                # Bit ops cannot address An, so mode 001 here is MOVEP <-> d16(Ay): a 16-bit
                # displacement follows, making it 4 bytes. Read as a 2-byte "btst d0,a0" it
                # both prints an impossible form and desyncs the sweep from there on.
                sz = ".l" if opmode & 1 else ".w"
                mem = "%d(a%d)" % (s16(rd16(d, p + 2)), r)
                if opmode & 2:  # opmode 110/111: register -> memory
                    return 4, "movep%s d%d,%s" % (sz, dn, mem)
                return 4, "movep%s %s,d%d" % (sz, mem, dn)
            names = ["btst", "bchg", "bclr", "bset"]
            t, c = ea(d, p + 2, m, r, 0, pc2)
            return 2 + c, "%s d%d,%s" % (names[opmode], dn, t)

    # ---- line 4: misc ----
    if top == 4:
        exact = {0x4e71: "nop", 0x4e75: "rts", 0x4e73: "rte", 0x4e77: "rtr",
                 0x4e70: "reset", 0x4e76: "trapv", 0x4afc: "illegal"}
        if w in exact:
            return 2, exact[w]
        if w == 0x4e72:  # STOP #imm
            return 4, "stop #$%x" % rd16(d, p + 2)
        if 0x4e40 <= w <= 0x4e4f:
            return 2, "trap #%d" % (w & 0xf)
        if 0x4e50 <= w <= 0x4e57:
            return 4, "link a%d,#$%x" % (w & 7, rd16(d, p + 2))
        if 0x4e58 <= w <= 0x4e5f:
            return 2, "unlk a%d" % (w & 7)
        if 0x4e60 <= w <= 0x4e67:
            return 2, "move a%d,usp" % (w & 7)
        if 0x4e68 <= w <= 0x4e6f:
            return 2, "move usp,a%d" % (w & 7)
        if (w & 0xffc0) == 0x4e80 or (w & 0xffc0) == 0x4ec0:
            mn = "jsr" if (w & 0xffc0) == 0x4e80 else "jmp"
            t, c = ea(d, p + 2, (w >> 3) & 7, w & 7, 2, pc2)
            return 2 + c, "%s %s" % (mn, t)
        # EXT
        if (w & 0xfff8) == 0x4880: return 2, "ext.w d%d" % (w & 7)
        if (w & 0xfff8) == 0x48c0: return 2, "ext.l d%d" % (w & 7)
        # MOVEM
        if (w & 0xfb80) == 0x4880:
            sz = ".l" if (w >> 6) & 1 else ".w"
            load = (w >> 10) & 1
            mask = rd16(d, p + 2)
            t, c = ea(d, p + 4, (w >> 3) & 7, w & 7, 2, pc2 + 2)
            if load:
                return 4 + c, "movem%s %s,#$%04x" % (sz, t, mask)
            return 4 + c, "movem%s #$%04x,%s" % (sz, mask, t)
        # SWAP / PEA
        if (w & 0xfff8) == 0x4840: return 2, "swap d%d" % (w & 7)
        if (w & 0xffc0) == 0x4840:
            t, c = ea(d, p + 2, (w >> 3) & 7, w & 7, 2, pc2)
            return 2 + c, "pea %s" % t
        # LEA
        if (w & 0xf1c0) == 0x41c0:
            t, c = ea(d, p + 2, (w >> 3) & 7, w & 7, 2, pc2)
            return 2 + c, "lea %s,a%d" % (t, (w >> 9) & 7)
        # CLR/NEG/NEGX/NOT/TST + TAS
        onea = {0x40: "negx", 0x42: "clr", 0x44: "neg", 0x46: "not", 0x4a: "tst"}
        hi = (w >> 8) & 0xff
        if w == 0x4ac0 or ((w & 0xffc0) == 0x4ac0):
            t, c = ea(d, p + 2, (w >> 3) & 7, w & 7, 0, pc2)
            return 2 + c, "tas %s" % t
        if hi in onea:
            size = (w >> 6) & 3
            if size == 3:
                pass
            else:
                t, c = ea(d, p + 2, (w >> 3) & 7, w & 7, size, pc2)
                return 2 + c, "%s%s %s" % (onea[hi], SZC[size], t)

    # ---- line 5: ADDQ/SUBQ/Scc/DBcc ----
    if top == 5:
        if (w & 0x00c0) == 0x00c0:
            if (w & 0x0038) == 0x0008:  # DBcc
                tgt = (pc2 + s16(rd16(d, p + 2))) & 0xffffff
                return 4, "db%s d%d,$%x" % (CC2[(w >> 8) & 0xf], w & 7, tgt)
            t, c = ea(d, p + 2, (w >> 3) & 7, w & 7, 0, pc2)  # Scc
            return 2 + c, "s%s %s" % (CC2[(w >> 8) & 0xf], t)
        size = (w >> 6) & 3
        data = (w >> 9) & 7 or 8
        mn = "subq" if (w >> 8) & 1 else "addq"
        t, c = ea(d, p + 2, (w >> 3) & 7, w & 7, size, pc2)
        return 2 + c, "%s%s #%d,%s" % (mn, SZC[size], data, t)

    # ---- lines 8,9,B,C,D: OR/SUB/CMP-EOR/AND/ADD (+A forms) ----
    if top in (8, 9, 0xb, 0xc, 0xd):
        base_mn = {8: "or", 9: "sub", 0xb: "cmp", 0xc: "and", 0xd: "add"}[top]
        opmode = (w >> 6) & 7
        reg = (w >> 9) & 7
        m, r = (w >> 3) & 7, w & 7
        if opmode in (3, 7):
            muldiv = MULDIV.get((top, opmode))
            if muldiv:  # MULU/MULS/DIVU/DIVS: source is always word-sized, dest is Dn
                t, c = ea(d, p + 2, m, r, 1, pc2)
                return 2 + c, "%s.w %s,d%d" % (muldiv, t, reg)
            size = 1 if opmode == 3 else 2  # SUBA/CMPA/ADDA: <ea> -> An, word / long
            t, c = ea(d, p + 2, m, r, size, pc2)
            amn = {9: "suba", 0xb: "cmpa", 0xd: "adda"}[top]
            return 2 + c, "%s%s %s,a%d" % (amn, SZC[size], t, reg)
        if (top, opmode, m) in EXG_FORMS:  # EXG hides in AND's "Dn -> <ea>" opmodes
            return 2, EXG_FORMS[(top, opmode, m)] % (reg, r)
        pair = pair_op(top, opmode, m, reg, r)  # ...and the ADDX/SUBX/ABCD/SBCD/CMPM family below
        if pair:
            return 2, pair
        size = opmode & 3
        t, c = ea(d, p + 2, m, r, size, pc2)
        mn = "eor" if (top == 0xb and opmode >= 4) else base_mn
        if opmode < 3:  # ea -> Dn
            return 2 + c, "%s%s %s,d%d" % (mn, SZC[size], t, reg)
        return 2 + c, "%s%s d%d,%s" % (mn, SZC[size], reg, t)

    # ---- line E: shifts/rotates ----
    if top == 0xe:
        names = ["as", "ls", "rox", "ro"]
        if (w & 0x00c0) == 0x00c0:  # memory shift by 1
            t, c = ea(d, p + 2, (w >> 3) & 7, w & 7, 1, pc2)
            mn = names[(w >> 9) & 3] + ("l" if (w >> 8) & 1 else "r")
            return 2 + c, "%s.w %s" % (mn, t)
        mn = names[(w >> 3) & 3] + ("l" if (w >> 8) & 1 else "r")
        cnt = (w >> 9) & 7
        src = "#%d" % (cnt or 8) if not ((w >> 5) & 1) else "d%d" % cnt
        return 2, "%s%s %s,d%d" % (mn, SZC[(w >> 6) & 3], src, w & 7)

    # ---- line A / line F ----
    if top == 0xa: return 2, "dc.w $%04x  ; line-A" % w
    if top == 0xf: return 2, "dc.w $%04x  ; line-F" % w

    return 2, "dc.w $%04x" % w


def disasm(d, h, start, length, fixes, base=0):
    # decode() maps file offset -> image address via (p - 28); `base` shifts that to
    # the address the program actually runs at (0 = image offsets, the default).
    p, end = start, start + length
    prev_imm = None  # last "move.w #imm,-(sp)" value, for trap naming
    out = []
    while p < end:
        img_off = p - 28          # offset within the loaded image (what `fixes` indexes)
        addr = img_off + base     # address the instruction runs at
        try:
            n, txt = decode(d, p, base)
        except Exception as e:
            n, txt = 2, "dc.w $%04x  ; <decode err %s>" % (rd16(d, p), e)
        # trap annotation
        w = rd16(d, p)
        if 0x4e40 <= w <= 0x4e4f:
            vec = w & 0xf
            if vec in TRAPVEC and prev_imm is not None:
                nm, tbl = TRAPVEC[vec]
                fn = tbl.get(prev_imm, "?")
                txt += "   ; %s %s ($%x)" % (nm, fn, prev_imm)
        m = None
        if (w & 0xffff) == 0x3f3c:  # move.w #imm,-(sp)
            prev_imm = rd16(d, p + 2)
        elif w not in (0x4e71,):
            # keep prev_imm across a trailing addq etc.; reset only on new push seq
            pass
        # reloc flag: any of this insn's bytes at a fixed longword?
        relmark = ""
        for off in range(img_off, img_off + n, 2):
            if off in fixes:
                relmark = "  <RELOC ptr>"
                break
        raw = d[p:p + n].hex()
        out.append("%06x: %-20s %-34s%s" % (addr, raw, txt, relmark))
        p += n
    return "\n".join(out)


def show_strings(d, s, e, minlen=4):
    res, cur, start = [], b"", s
    for i in range(s, e):
        c = d[i]
        if 32 <= c < 127:
            if not cur:
                start = i
            cur += bytes([c])
        else:
            if len(cur) >= minlen:
                res.append((start - 28, cur.decode("latin1")))
            cur = b""
    if len(cur) >= minlen:
        res.append((start - 28, cur.decode("latin1")))
    return res


def _entropy(b):
    """Shannon entropy (bits/byte) — a quick 'is it packed?' signal."""
    import math
    from collections import Counter
    if not b:
        return 0.0
    n = len(b)
    return -sum(c / n * math.log2(c / n) for c in Counter(b).values())


def main():
    path = sys.argv[1]
    d = open(path, "rb").read()
    h = parse_header(d)
    fixes = parse_reloc(d, h)
    code_start, code_len = 28, h["tlen"]
    base = int(sys.argv[sys.argv.index("--base") + 1], 0) if "--base" in sys.argv else 0
    print("=" * 78)
    print("FILE %s  (%d bytes)" % (path, len(d)))
    print("text=0x%x data=0x%x bss=0x%x sym=0x%x  reloc entries=%d" %
          (h["tlen"], h["dlen"], h["blen"], h["slen"], len(fixes)))
    ent = _entropy(d[28:28 + h["tlen"]])
    hint = "LIKELY PACKED (analyze the loader / dump from Hatari)" if ent > 6.7 \
        else "looks like plain code+data"
    print("text entropy=%.2f bits/byte  -> %s" % (ent, hint))
    print("LOAD BASE = 0x%x  -> every address below is %s" %
          (base, "a RUNTIME address (image offset + base)" if base
           else "an IMAGE OFFSET (pass --base to get runtime addresses)"))
    print("=" * 78)

    if "--data" in sys.argv:
        ds, de = 28 + h["tlen"], 28 + h["tlen"] + h["dlen"]
        print("\n--- DATA segment strings (addr = image offset) ---")
        for off, st in show_strings(d, ds, de):
            print("  %06x  %r" % (off, st))
        return

    print("\n--- strings anywhere in file ---")
    for off, st in show_strings(d, 0, len(d)):
        print("  %06x  %r" % (off + base, st))

    st = int(sys.argv[sys.argv.index("--start") + 1], 0) if "--start" in sys.argv else code_start
    ln = int(sys.argv[sys.argv.index("--len") + 1], 0) if "--len" in sys.argv else code_len
    print("\n--- first-pass disassembly (text: addr 0x%x..0x%x) ---" % (base, base + code_len))
    print(disasm(d, h, st, ln, fixes, base))


if __name__ == "__main__":
    main()