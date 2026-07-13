"""ISA conformance suite (#5): cross-validate the Musashi oracle against a genuine 68000.

We can't diff a whole program run against real TOS (Musashi runs at a fixed base, TOS Pexecs at
a machine-dependent TPA — see the plan). Instead we validate the *CPU core itself*: run a catalog
of small, self-contained 68000 instruction snippets on BOTH Musashi and Hatari's independent
(WinUAE-derived) 68000, and compare. Agreement between two independent, hardware-validated cores
is strong evidence that "verified against Musashi" means "verified against a real 68000" — for the
exact instruction mix BuggyBoy uses (byte/word memory RMW, asr/lsl, ext, muls/divs, addx, cmp+scc).

Each case is *position-independent*: inputs are immediates, the flags (CCR) are captured with
`move sr,(a5)+` immediately after the instruction under test, then the 32-bit result is saved via
`(a5)+`. The identical bytes therefore run at any address on either core — no relocation, and no
shim change (the existing emu.run and tos_probe suffice). Only CCR bits X N Z V C are compared;
the SR mode bits differ (Musashi runs supervisor, a TOS program runs user).
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import emu                       # noqa: E402
import tos_probe                 # noqa: E402  (reuse _Asm + the headless-Hatari runner)
from loader import IMAGE_SIZE    # noqa: E402

CODE = 0x10000                   # Musashi: run the blob here
REC = 0x30000                    # Musashi: a5 output cursor (record grows up from here)
SCRATCH = 0x30800                # Musashi: a6 byte/word/long memory scratch (clear of the record)
CCR = 0x1f                       # compare only X N Z V C; SR mode bits differ by privilege level
CASE_BYTES = 6                   # per case: SR word (captured first) + 32-bit result


def _w(v):
    return struct.pack(">H", v & 0xffff)


def _l(v):
    return struct.pack(">I", v & 0xffffffff)


# ---- instruction byte-emitters (verified against the 68000 ISA; see comments) ----
def movei_l(d, imm):  return _w(0x203c | (d << 9)) + _l(imm)     # move.l #imm,dN
def movei_b(d, imm):  return _w(0x103c | (d << 9)) + _w(imm)     # move.b #imm,dN
def set_ccr(v):       return _w(0x44fc) + _w(v)                  # move.w #v,ccr (X N Z V C)
def cap_sr():         return _w(0x40dd)                          # move.w sr,(a5)+  (capture flags)
def save_l(d):        return _w(0x2ac0 | d)                      # move.l dN,(a5)+
def save_a(a):        return _w(0x2ac8 | a)                      # move.l aN,(a5)+
def scratch_b(v):     return _w(0x1cbc) + _w(v)                  # move.b #v,(a6)
def scratch_w(v):     return _w(0x3cbc) + _w(v)                  # move.w #v,(a6)
def scratch_l(v):     return _w(0x2cbc) + _l(v)                  # move.l #v,(a6)
def save_mem_b():     return _w(0x7e00) + _w(0x1e16) + save_l(7)  # moveq#0,d7; move.b(a6),d7; save
def save_mem_w():     return _w(0x7e00) + _w(0x3e16) + save_l(7)  # moveq#0,d7; move.w(a6),d7; save
def save_mem_l():     return _w(0x2e16) + save_l(7)              # move.l(a6),d7; save


def shift(cnt, dr, size, typ, d):
    """1110 ccc d ss 0 tt rrr — immediate-count shift/rotate. cnt 1..8 (8 encodes as 0),
    dr 0=right/1=left, size 0/1/2 = b/w/l, typ 0=AS 1=LS 2=ROX 3=RO."""
    return _w(0xe000 | ((cnt & 7) << 9) | (dr << 8) | (size << 6) | (typ << 3) | d)


def quick_mem(sub, n, size):
    """addq/subq #n to (a6): 0101 nnn s ss 010110  (s=1 subq, size 0/1/2 = b/w/l)."""
    return _w(0x5000 | ((n & 7) << 9) | (sub << 8) | (size << 6) | 0x16)


# ---- a case: setup (immediates) + test instruction + capture(SR, then result) ----
class Case:
    def __init__(self, name, setup, test, result, ccr_mask=CCR):
        self.name, self.setup, self.test, self.result = name, setup, test, result
        self.ccr_mask = ccr_mask                 # which CCR bits are *defined* and thus comparable

    def emit(self):
        kind = self.result
        if kind[0] == "reg":
            save = save_l(kind[1])
        elif kind[0] == "areg":
            save = save_a(kind[1])
        else:
            save = {"mem_b": save_mem_b, "mem_w": save_mem_w, "mem_l": save_mem_l}[kind[0]]()
        return self.setup + self.test + cap_sr() + save


# ---- the catalog: generators for each divergence-prone class ----
_SVALS = (0x80000001, 0x0000ffff, 0x55555555, 0x00000001, 0x7fffffff)
_MEMB = (0x00, 0x01, 0x7f, 0x80, 0xff)


def _catalog():
    cases = []

    def add(name, setup, test, result, ccr_mask=CCR):
        cases.append(Case(name, setup, test, result, ccr_mask))

    # 1) shifts / rotates (long): AS/LS/ROX/RO, both directions, counts 1/3/8. ROX reads X.
    names = {0: "as", 1: "ls", 2: "rox", 3: "ro"}
    for typ in (0, 1, 2, 3):
        for dr in (0, 1):
            for cnt in (1, 3, 8):
                for v in _SVALS:
                    x = 0x10 if typ == 2 else 0        # ROX consumes X: pin it
                    add(f"{names[typ]}{'rl'[dr]}.l #{cnt},{v:#010x}",
                        set_ccr(x) + movei_l(0, v), shift(cnt, dr, 2, typ, 0), ("reg", 0))

    # 2) byte/word/long memory read-modify-write (the class Unicorn mis-handled)
    for init in _MEMB:
        add(f"addq.b #1,(mem)={init:#04x}", set_ccr(0) + scratch_b(init), quick_mem(0, 1, 0), ("mem_b",))
        add(f"subq.b #1,(mem)={init:#04x}", set_ccr(0) + scratch_b(init), quick_mem(1, 1, 0), ("mem_b",))
        add(f"addq.b #8,(mem)={init:#04x}", set_ccr(0) + scratch_b(init), quick_mem(0, 8, 0), ("mem_b",))
        add(f"neg.b (mem)={init:#04x}", set_ccr(0) + scratch_b(init), _w(0x4416), ("mem_b",))
        add(f"not.b (mem)={init:#04x}", set_ccr(0) + scratch_b(init), _w(0x4616), ("mem_b",))
        add(f"add.b #0x7f,(mem)={init:#04x}",
            set_ccr(0) + scratch_b(init) + movei_b(1, 0x7f), _w(0xd316), ("mem_b",))  # add.b d1,(a6)
    for init in (0x0000, 0x7fff, 0x8000, 0xffff):
        add(f"subq.w #1,(mem)={init:#06x}", set_ccr(0) + scratch_w(init), quick_mem(1, 1, 1), ("mem_w",))
    for init in (0x00000000, 0x7fffffff, 0x80000000, 0xffffffff):
        add(f"addq.l #1,(mem)={init:#010x}", set_ccr(0) + scratch_l(init), quick_mem(0, 1, 2), ("mem_l",))

    # 3) sign / zero extension
    for v in (0x00000000, 0x0000007f, 0x00000080, 0x000000ff, 0x00007fff, 0x00008000, 0x0000ffff):
        add(f"ext.w {v:#010x}", set_ccr(0) + movei_l(0, v), _w(0x4880), ("reg", 0))
        add(f"ext.l {v:#010x}", set_ccr(0) + movei_l(0, v), _w(0x48c0), ("reg", 0))
    for v in (0x0001, 0x7fff, 0x8000, 0xffff):
        add(f"movea.w #{v:#06x},a0", set_ccr(0), _w(0x307c) + _w(v), ("areg", 0))    # sign-extends

    # 4) multiply / divide (never divide by zero -> would trap)
    for v in (0x00008000, 0x0000ffff, 0x00000002, 0x00007fff):
        for imm in (3, 0xfffd, 0x0100):                                             # 0xfffd = -3
            add(f"muls.w #{imm:#06x},{v:#010x}", set_ccr(0) + movei_l(0, v),
                _w(0xc1fc) + _w(imm), ("reg", 0))
            add(f"mulu.w #{imm:#06x},{v:#010x}", set_ccr(0) + movei_l(0, v),
                _w(0xc0fc) + _w(imm), ("reg", 0))
    for dividend in (0x00010000, 0x7fffffff, 0x00000064, 0x80000000):
        for imm in (3, 0xfffd, 0x0007, 0x0001):
            # N and Z are officially *undefined* after a DIVS/DIVU overflow (68000 PRM); the two
            # cores legitimately differ there (Musashi leaves N=0, WinUAE sets it). Compare only
            # the defined bits X V C — the result and the overflow flag (V) still must agree.
            add(f"divs.w #{imm:#06x},{dividend:#010x}", set_ccr(0) + movei_l(0, dividend),
                _w(0x81fc) + _w(imm), ("reg", 0), ccr_mask=0x13)
            add(f"divu.w #{imm:#06x},{dividend:#010x}", set_ccr(0) + movei_l(0, dividend),
                _w(0x80fc) + _w(imm), ("reg", 0), ccr_mask=0x13)

    # 5) arithmetic + condition codes
    pairs = ((0x7fffffff, 0x00000001), (0x80000000, 0x00000001), (0xffffffff, 0x00000001),
             (0x12345678, 0xdeadbeef), (0x00000000, 0x00000000))
    for a, b in pairs:
        add(f"add.l {a:#010x},{b:#010x}", set_ccr(0) + movei_l(0, a) + movei_l(1, b),
            _w(0xd081), ("reg", 0))                     # add.l d1,d0
        add(f"sub.l {a:#010x},{b:#010x}", set_ccr(0) + movei_l(0, a) + movei_l(1, b),
            _w(0x9081), ("reg", 0))                     # sub.l d1,d0
        for xin in (0, 0x10):                           # addx/subx consume X
            add(f"addx.l x={xin:#x} {a:#010x},{b:#010x}",
                set_ccr(xin) + movei_l(0, a) + movei_l(1, b), _w(0xd181), ("reg", 0))
            add(f"subx.l x={xin:#x} {a:#010x},{b:#010x}",
                set_ccr(xin) + movei_l(0, a) + movei_l(1, b), _w(0x9181), ("reg", 0))

    # the signed cmp.b + Scc idiom add_score relies on ('9' - digit, branch if minus)
    for digit in (0x2f, 0x30, 0x39, 0x3a, 0x7f, 0x80, 0xff):
        add(f"cmp.b '9',{digit:#04x}; smi", set_ccr(0) + movei_l(0, 0x39) + movei_b(1, digit),
            _w(0xb001) + _w(0x5bc2), ("reg", 2))        # cmp.b d1,d0 ; smi d2

    # swap / neg / not
    for v in (0x00000001, 0x80000000, 0xffff0000, 0x12345678):
        add(f"swap {v:#010x}", set_ccr(0) + movei_l(0, v), _w(0x4840), ("reg", 0))
        add(f"neg.l {v:#010x}", set_ccr(0) + movei_l(0, v), _w(0x4480), ("reg", 0))

    return cases


CATALOG = _catalog()


def build_blob():
    """Concatenated case bytes (no trailing rts). Returns (blob, names)."""
    blob = b"".join(c.emit() for c in CATALOG)
    return blob, [c.name for c in CATALOG]


def _parse(rec, n):
    return [(struct.unpack_from(">I", rec, i * CASE_BYTES + 2)[0],       # 32-bit result
             struct.unpack_from(">H", rec, i * CASE_BYTES)[0] & CCR)     # CCR bits
            for i in range(n)]


def run_musashi(blob, n):
    img = bytearray(IMAGE_SIZE)
    img[CODE:CODE + len(blob)] = blob + b"\x4e\x75"          # + rts -> returns to the sentinel
    mem, _, _ = emu.run(img, CODE, {"a5": REC, "a6": SCRATCH}, max_insns=1_000_000)
    return _parse(bytes(mem[REC:REC + n * CASE_BYTES]), n)


def _build_tos(blob, record_len):
    a = tos_probe._Asm()
    a.mshrink_prologue()
    a.push_l(0x2000); a.push_w(0x48); a.trap(1); a.pop(6)    # Malloc(0x2000) -> d0
    a.d0_to_areg(4); a.d0_to_areg(5)                         # a4 = record base, a5 = cursor
    a.lea(0x1000, 4, 6)                                      # a6 = a4 + 0x1000 (memory scratch)
    a.b += blob                                              # the shared, position-independent cases
    a.push_w(0); out_fix = a.pea_pc_fixup(); a.push_w(0x3c); a.trap(1); a.pop(8); a.d0_to_d6()
    a.push_areg(4); a.push_l(record_len); a.push_d6(); a.push_w(0x40); a.trap(1); a.pop(12)  # Fwrite
    a.push_d6(); a.push_w(0x3e); a.trap(1); a.pop(4)         # Fclose
    a.push_w(0); a.trap(1)                                   # Pterm0
    out_off = a.off; a.b += b"OUT.BIN\0"; a.patch_pea(out_fix, out_off)
    text = bytes(a.b)
    return struct.pack(">HIIIIIIH", 0x601a, len(text), 0, 0, 0, 0, 0, 0) + text + b"\x00\x00\x00\x00"


def run_hatari(blob, n):
    record_len = n * CASE_BYTES
    rec = tos_probe.run_tos_program(_build_tos(blob, record_len), record_len)
    return _parse(rec, n)


def compare():
    """Run the catalog on both cores; return (mismatches, n). Each mismatch is (name, m, h).
    Compares the 32-bit result exactly and only the *defined* CCR bits (per-case ccr_mask)."""
    blob, names = build_blob()
    n = len(names)
    m, h = run_musashi(blob, n), run_hatari(blob, n)
    mismatches = []
    for i, c in enumerate(CATALOG):
        (mr, mc), (hr, hc) = m[i], h[i]
        if mr != hr or (mc & c.ccr_mask) != (hc & c.ccr_mask):
            mismatches.append((c.name, m[i], h[i]))
    return mismatches, n


if __name__ == "__main__":
    if not tos_probe.available():
        print("Hatari/TOS not available")
        sys.exit(0)
    bad, total = compare()
    for name, mc, hc in bad:
        print(f"  DIFF {name:32}  musashi=(res={mc[0]:#010x} ccr={mc[1]:#04x})  "
              f"hatari=(res={hc[0]:#010x} ccr={hc[1]:#04x})")
    print(f"{total - len(bad)}/{total} cases match" + ("" if bad else "  — ALL MATCH"))
