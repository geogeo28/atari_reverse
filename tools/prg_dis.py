#!/usr/bin/env python3
"""Reloc-aware GEMDOS .PRG analyzer + first-pass 68000 linear-sweep disassembler.

Stdlib only. Priority is *correct instruction length* (via 68000 effective-address
extension-word rules) so the linear sweep does not desync; mnemonic fidelity is
"good enough for a first pass" — refine in Ghidra. Traps are auto-named, and
longwords listed in the relocation table are flagged (they are absolute pointers,
i.e. future labels).

Usage: python3 prg_dis.py FILE.PRG [--data] [--start OFF] [--len N]
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
XBIOS = {0x00: "Initmous", 0x02: "Physbase", 0x03: "Logbase", 0x04: "Getrez",
         0x05: "Setscreen", 0x06: "Setpalette", 0x07: "Setcolor", 0x08: "Floprd",
         0x09: "Flopwr", 0x0E: "Setprt", 0x0F: "Setpad?", 0x11: "Random",
         0x14: "Scrdmp", 0x18: "Kbdvbase", 0x1F: "Vsync", 0x20: "Supexec",
         0x21: "Puntaes", 0x26: "Supexec", 0x28: "Xbtimer", 0x2A: "Dosound"}
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
        if b == 0:
            break
        if b == 1:
            cur += 254
        else:
            cur += b
            fixes.add(cur)
    return fixes


# --- effective-address decoding: returns (text, extra_bytes_consumed) -----------
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
        if (w & 0x0100):  # dynamic bit op with Dn
            bit = (w >> 6) & 3
            names = ["btst", "bchg", "bclr", "bset"]
            m, r = (w >> 3) & 7, w & 7
            t, c = ea(d, p + 2, m, r, 0, pc2)
            return 2 + c, "%s d%d,%s" % (names[bit], (w >> 9) & 7, t)

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
        if opmode in (3, 7):  # Ea forms: word / long
            size = 1 if opmode == 3 else 2
            t, c = ea(d, p + 2, m, r, size, pc2)
            amn = {8: "or", 9: "suba", 0xb: "cmpa", 0xc: "and", 0xd: "adda"}[top]
            return 2 + c, "%s%s %s,a%d" % (amn, SZC[size], t, reg)
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


def disasm(d, h, start, length, fixes):
    base = 0  # pc2 already maps file offset -> image address via (p - 28)
    p, end = start, start + length
    prev_imm = None  # last "move.w #imm,-(sp)" value, for trap naming
    out = []
    while p < end:
        addr = p - 28  # address within loaded image (text base = 0)
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
        for off in range(addr, addr + n, 2):
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
    print("=" * 78)
    print("FILE %s  (%d bytes)" % (path, len(d)))
    print("text=0x%x data=0x%x bss=0x%x sym=0x%x  reloc entries=%d" %
          (h["tlen"], h["dlen"], h["blen"], h["slen"], len(fixes)))
    ent = _entropy(d[28:28 + h["tlen"]])
    hint = "LIKELY PACKED (analyze the loader / dump from Hatari)" if ent > 6.7 \
        else "looks like plain code+data"
    print("text entropy=%.2f bits/byte  -> %s" % (ent, hint))
    print("=" * 78)

    if "--data" in sys.argv:
        ds, de = 28 + h["tlen"], 28 + h["tlen"] + h["dlen"]
        print("\n--- DATA segment strings (addr = image offset) ---")
        for off, st in show_strings(d, ds, de):
            print("  %06x  %r" % (off, st))
        return

    print("\n--- strings anywhere in file ---")
    for off, st in show_strings(d, 0, len(d)):
        print("  %06x  %r" % (off, st))

    st = int(sys.argv[sys.argv.index("--start") + 1], 0) if "--start" in sys.argv else code_start
    ln = int(sys.argv[sys.argv.index("--len") + 1], 0) if "--len" in sys.argv else code_len
    print("\n--- first-pass disassembly (text: addr 0x0..0x%x) ---" % code_len)
    print(disasm(d, h, st, ln, fixes))


if __name__ == "__main__":
    main()