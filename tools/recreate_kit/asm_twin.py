"""Run a project's hand-written m68k ASM TWINS under Musashi, over the same image its C cores use.

A twin is a `src/asm/*.S` transcription of the ORIGINAL binary's own instruction sequence for one
routine, carrying the SAME C signature as the verified C core it replaces on the target build. The C
core stays the reference; this module is what proves the twin equals it.

WHY THIS IS NOT THE ORACLE. `oracle/emu.py:run()` executes the ORIGINAL program in place, at its own
addresses, and `harness.differential()` compares the C candidate against it. A twin is neither: it is
OUR m68k code, linked at its own base, called through the C ABI. So it needs its own runner — this
one — and its own comparison, which is against the C core rather than against the original. The chain
that results is:

    original  ==(harness.differential)==  C core  ==(this module)==  asm twin

and each link is byte-exact over the whole image, so the twin is pinned to the original transitively
without ever needing a second oracle run.

THE MEMORY LAYOUT, and why nothing about it is shared with the `.S`:

    0                    the twin blob, linked at base 0 (`-Ttext=0`, ASM_LINK_BASE below)
    ...                  a stack, above the blob's end
    ...                  ZEROED PAD, checked after every call -- a walk backwards off the image
    image_at             the project's flat image (loader.IMAGE_SIZE bytes) -- arg0
    ...                  ZEROED BAND, checked after every call -- a walk forwards off the image
    sentinel             the return address run_bench watches for

The `.S` files are linked at 0 and know nothing of where the image lands: they receive its base as
their first C argument, exactly as they do in the target build where it is a real pointer. `image_at`
is therefore NON-ZERO here ON PURPOSE. A twin that ignored its base argument and addressed the image
absolutely (the shape the original itself uses, since the original IS the image) would still pass a
differential run at base 0 -- and would fault the moment the target build handed it a real pointer.
Placing the image high is the one arrangement in which that mistake cannot survive the suite.

Usage (see projects/zynaps/recreate/test/test_asm_scroll.py for the worked case):

    twins = AsmTwins(build_dir / "asm")          # loads twins.elf + twins.bin once
    out   = twins.call(image, "scroll_emit_column_shift2_asm", workspace, page, edge)
    assert out.image == c_core_image             # byte-exact over the WHOLE image
"""
import subprocess
from pathlib import Path

# The `.S` files are linked here by the kit's Makefile rule (kit.mk, $(ASM_ELF)). Spelt once, in
# Python, and passed to the linker from there -- see asm_link_base() below, which is what kit.mk
# reads -- so the blob's base cannot drift from the loader's idea of it.
ASM_LINK_BASE = 0

# Room for the twin's own stack, between the blob's end and the image. A twin's frame is a movem of
# the callee-saved file plus a handful of longs; 64 KiB is three orders of magnitude of headroom and
# costs nothing (the bytearray is allocated once per call either way).
ASM_STACK_BYTES = 0x10000

# The image is placed on a 1 MiB boundary past the stack. Round, non-zero, and above every address a
# twin could reach by mistaking an image offset for an absolute address -- so such a mistake lands in
# the gap and is caught, rather than aliasing a real image byte.
IMAGE_ALIGN = 0x100000

# A zeroed band ABOVE the image, checked after every call. The image comparison against the C core
# stops at the image's last byte, so a twin whose span is one row or one word too generous writes
# where there is nothing to differ -- the same blind spot `make guarded` exists to close on the C
# side, and one a twin has no PROT_NONE sweep for.
#
# BOTH SIDES ARE CHECKED, not just this one. A twin that walks BACKWARDS one row too far is as
# ordinary a defect as one that walks forward -- the vertically flipped tile arms step with a
# negative displacement throughout -- and it lands in the pad BELOW the image, which the alignment
# leaves free. `make guarded` is two-sided for the same reason; a one-sided stand-in would have been
# advertised as something it was not.
#
# 64 KiB, which is not a game's shape: the band's job is to be wider than one routine's overrun, and
# `call()` additionally checks every byte from the band's end to the sentinel, so an overrun WIDER
# than the band is caught too rather than sailing past it.
IMAGE_GUARD_BYTES = 0x10000


def asm_link_base():
    """The text base kit.mk links the twins at. Printed for the Makefile so there is one spelling."""
    return ASM_LINK_BASE


class TwinResult:
    """One twin run: the image it produced, its return value, and what it cost."""

    def __init__(self, image, d0, cycles, ninsns):
        self.image = image
        self.d0 = d0
        self.cycles = cycles
        self.ninsns = ninsns


class AsmTwins:
    """The assembled twins for one project, loaded once and callable with the C ABI.

    `asm_dir` holds `twins.elf` (for the symbol table) and `twins.bin` (the flat blob), both built by
    kit.mk's $(ASM_BIN) rule from that project's `src/asm/*.S`.
    """

    def __init__(self, asm_dir, image_size):
        self.elf = Path(asm_dir) / "twins.elf"
        self.bin = Path(asm_dir) / "twins.bin"
        self.require()
        self.symbols = {name: value for name, (value, _) in elf_symbols(self.elf).items()}
        blob = self.bin.read_bytes()

        self.image_size = image_size
        stack_top = _align(ASM_LINK_BASE + len(blob) + ASM_STACK_BYTES, 16)
        self.stack_top = stack_top
        self.image_at = _align(stack_top + 16, IMAGE_ALIGN)
        self.image_guard_end = self.image_at + image_size + IMAGE_GUARD_BYTES
        self.sentinel = self.image_guard_end + 0x10

        # The template every call copies: the blob in place, everything else zero. Sized to hold the
        # sentinel word itself, since run_bench compares the PC against it after an `rts` lands there.
        self._template = bytearray(self.sentinel + 0x10)
        self._template[ASM_LINK_BASE:ASM_LINK_BASE + len(blob)] = blob
        self._blob_span = (ASM_LINK_BASE, ASM_LINK_BASE + len(blob))

    def require(self):
        """FAIL LOUDLY if the twins were never assembled. A skip here would hide a broken twin: the
        suite would go green having compared nothing, which is the one outcome a differential must
        not have."""
        missing = [p for p in (self.elf, self.bin) if not p.exists()]
        if missing:
            raise FileNotFoundError(
                f"the asm twins are not built ({', '.join(p.name for p in missing)} missing) -- "
                f"build them with `make test` (or `make {self.bin}`), which assembles src/asm/*.S")

    def entry(self, symbol):
        """A symbol's link address, or a listing of what WAS assembled — a renamed or dropped twin
        must name itself rather than surface as a wild jump to 0.

        The listing is of NEIGHBOURS by suffix rather than of twins: callers ask for `_body` /
        `_body_end` bracket labels as well as for `_asm` entry points, and a listing that named only
        the twins would omit exactly the symbols a missing bracket needs it to show.
        """
        try:
            return self.symbols[symbol]
        except KeyError:
            suffix = symbol.rsplit("_", 1)[-1]
            near = sorted(s for s in self.symbols if s.endswith(suffix))
            known = ", ".join(near) if near else ", ".join(sorted(self.symbols)) or "(none)"
            raise KeyError(f"no symbol {symbol!r} in the assembled twins; "
                           f"what is there: {known}") from None

    def call(self, image, symbol, *args):
        """Run `symbol` over a copy of `image` with the C ABI: the image base then `args`, each a
        32-bit stack word. Returns a TwinResult whose `.image` is the project image the twin left
        behind — compare it against the C core's, whole."""
        import emu

        if len(image) != self.image_size:
            raise ValueError(f"image is {len(image)} bytes, expected {self.image_size}")

        mem = bytearray(self._template)
        mem[self.image_at:self.image_at + self.image_size] = image
        # run_bench itself writes the return address at sp and arg0 at sp+4; the remaining C
        # arguments are the caller's to place, and they sit above those two longwords.
        for i, value in enumerate(args):
            at = self.stack_top + 8 + 4 * i
            mem[at:at + 4] = int(value & 0xffffffff).to_bytes(4, "big")

        r = emu.run_bench(mem, self.entry(symbol), arg0=self.image_at,
                          sp=self.stack_top, sentinel=self.sentinel)

        blob_lo, blob_hi = self._blob_span
        if mem[blob_lo:blob_hi] != self._template[blob_lo:blob_hi]:
            raise AssertionError(f"{symbol} stored into its own code — a wild write, not a divergence")
        # OUTSIDE THE IMAGE, ON BOTH SIDES, where the comparison against the C core has nothing to
        # compare. The C is run through `harness.candidate_image`, whose guarded sweep
        # (`make guarded`) faults on exactly this; a twin has no such sweep, so the surroundings are
        # kept zero and checked instead. A span one row too generous shows up here rather than
        # nowhere. Everything from the stack's top to the sentinel is covered bar the image itself,
        # so an overrun wider than the guard band is caught as well.
        # The lower band starts past the CALL FRAME, which is written on purpose: run_bench puts the
        # return address at `stack_top` and arg0 at `stack_top + 4`, and the remaining arguments sit
        # above those. Everything higher, up to the image, is the twin's to leave alone.
        frame_end = self.stack_top + 8 + 4 * len(args)
        for lo, hi, where in ((frame_end, self.image_at, "before the start of"),
                              (self.image_at + self.image_size, self.sentinel, "past the end of")):
            if any(mem[lo:hi]):
                raise AssertionError(
                    f"{symbol} stored {where} the image — a span one row or one word too generous, "
                    f"which the image comparison cannot see")

        return TwinResult(bytes(mem[self.image_at:self.image_at + self.image_size]),
                          r["d0"], r["cycles"], r["ninsns"])


def _align(value, to):
    return (value + to - 1) & ~(to - 1)


def elf_symbols(path):
    """{name: (value, type)} for every DEFINED symbol in an m68k object or executable.

    `nm` prints three fields for a defined symbol and two for an undefined one, so the length test is
    what separates them; the type letter is field two ('T' text, 'a' an absolute, i.e. a `.equ`).
    One parse, because there were three: this module wanted addresses, a project's constant pin wants
    `.equ` values, and both were reading the same tool's output through their own copy of the same
    four lines.
    """
    out = {}
    for line in subprocess.check_output(["m68k-elf-nm", str(path)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            out[parts[2]] = (int(parts[0], 16), parts[1])
    return out
