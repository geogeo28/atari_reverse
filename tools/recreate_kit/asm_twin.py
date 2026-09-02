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

A twin that CALLS a verified C core reaches it through the CALLBACK DOOR — see DOOR_BASE below and
TRAP_MODEL.md, "The callback door". The project hands its table in:

    twins = AsmTwins(build_dir / "asm", IMAGE_SIZE,
                     callbacks={0: DoorCallback("collision_chain_walk", 3)}, lib=harness._lib)
"""
import ctypes
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

# ---- THE CALLBACK DOOR: how a twin calls a verified C core (TRAP_MODEL.md, "The callback door") ----
#
# OFF TARGET ONLY, and that is the whole of what it is for. A twin transcribes the original's
# instructions, so it calls what the original calls — and some of those callees are C cores this
# side cannot link into the blob: they are HOST code (the candidate `.so`), and the seams two of
# them sit on (`sched_wait8`, `hw_bset8`) are modelled host-side as well, so an m68k build of them
# would model nothing. On the machine there is no problem to solve: the twin links against the real
# cores and its stub jumps straight to one. The door is the off-target stand-in for that link.
#
# WHAT IT IS NOT. It is not a trap, a syscall or a place to model anything. It is a PLAIN C CALL:
# the declared arguments off the emulated stack, the host function, the result in D0, the stub's
# `rts` — plus exactly what a REAL C call destroys on the way past: the caller-saved file
# (D0/D1/A0/A1) and every condition code, poisoned on purpose so a stub that forgot to save them
# fails here rather than on the machine. What the door does NOT do is model anything the two
# builds would then disagree about. Anything a call site needs beyond the call itself — the X
# flag in or out, a `tst.l` for a `beq` under it — belongs in the STUB,
# which exists in both builds; a door that did it would be doing it off target only, and the machine
# that ships would disagree with this harness about the 68000's flags with nothing here able to see
# it. An UNREGISTERED slot is a REFUSAL, never a fabricated 0: a twin calling a door nobody declared
# would otherwise pass on an answer no C core gave.
#
# THE BAND sits in the gap between the twin's stack top and the image, which is otherwise dead
# address space — `__init__` asserts that rather than trusting it, because a band that aliased the
# image or the stack would be a wrong answer with nothing to show for it. Slot `id` is one stride
# in, and the twin's stub is the only thing that names the address. Its simplest form, selected by
# `#ifdef RECREATE_HOST_DIFFERENTIAL` (kit.mk defines it for the off-target assembly only):
#
#     door_<name>:  jmp (0xf0000 + id*8).l      /* off target */
#     door_<name>:  jmp <name>                  /* on target — a TAIL jump, so the core's own
#                                                 * `rts` returns to the twin's call site */
#
# A stub may be fatter than that — Zynaps's `frame.S` stubs push the arguments, `jsr` the callee and
# regain control to unwind them and set the flag the original's callee answers in, which is exactly
# where such work belongs since the stub exists in both builds. All the door asks is the ordinary
# m68k SysV frame where it is reached: the return address at A7, the C arguments at A7+4, A7+8, ...
DOOR_BASE = 0x000F0000
DOOR_STRIDE = 8              # one `jmp (xxx).l` is 6 bytes; 8 keeps a slot's address readable
DOOR_SLOTS = 64
DOOR_SPAN = DOOR_SLOTS * DOOR_STRIDE


def asm_door_flags():
    """The band, as `-D` flags for the assembler. Read by kit.mk's ASM_CFLAGS.

    ASKED OF PYTHON rather than spelt again in a `.S`, for the reason `asm_link_base()` is: a second
    spelling drifts silently. A `.S` whose stub jumped to its own copy of an address the band had
    since moved would not stop at the door at all — it would EXECUTE the zeros there until the
    instruction cap, and fail as "did not return to the sentinel", naming neither the door nor the
    callee it was trying to reach.
    """
    return f"-DRECREATE_DOOR_BASE={DOOR_BASE:#x} -DRECREATE_DOOR_STRIDE={DOOR_STRIDE}"


# ---- THE CALLEE-SAVED FILE, and why a twin's is checked -------------------------------------
#
# The m68k SysV ABI's callee-saved registers. A twin saves them in a `movem` prologue and restores
# them in its epilogue, exactly as the original does — and NOTHING ELSE OFF TARGET LOOKS AT THEM.
# Measured on Zynaps's `draw_sprite_masked_asm`: drop `%d7` from both `movem` lists, correct the
# frame size to match, and `make test` stays green — the image is identical, the return value is
# identical, and the COST PIN GETS CHEAPER — while on the machine the twin returns with its caller's
# `%d7` holding a sprite's planes. The only surface left was a play-test, whose failure signature
# would not point at a `movem` list.
#
# So `call()` seeds each of them with a distinctive value and requires it back. The seed is a
# constant with a high byte no address or pixel word in this workspace has, plus the register's
# index, so a failure names the register that was lost rather than "a register".
#
# `%a5` and `%a6` are in the list like the rest. A twin may reserve them as base pointers — that is
# what they are for — but reserving one does not exempt it: it is still callee-saved, so the
# epilogue still has to put the caller's value back.
#
# WHAT SEEDING THE ADDRESS REGISTERS DOES NOT BUY, said plainly. A store through an address register
# the twin forgot to load now lands at 0xCA11ED0x, which is outside the emulated memory, and shim.c
# drops such a store — so it leaves no trace `call()` reads. It was never reliably caught before
# either: Musashi's reset does not clear D0-D7/A0-A6 (m68k_pulse_reset touches SR, VBR, A7 and PC and
# nothing else), so what such a register held was the PREVIOUS run's leftovers, and the "stored into
# its own code" check in `call()` caught the case only when those happened to be 0. The trade is a
# deterministic entry state for an accident, and the residual is recorded rather than claimed: what
# still catches an unloaded base register is the image comparison against the C core, which names a
# pixel diff rather than a register.
CALLEE_SAVED = ("d2", "d3", "d4", "d5", "d6", "d7", "a2", "a3", "a4", "a5", "a6")
CALLEE_SAVED_SEED = 0xCA11ED00

# {register: the value `call()` enters it with}. Built once: it is a constant, and `call()` needs the
# whole mapping on every call.
CALLEE_SAVED_SEEDS = {name: CALLEE_SAVED_SEED + i for i, name in enumerate(CALLEE_SAVED)}


class DoorCallback:
    """One C core a twin reaches through the door: its symbol in the project's candidate `.so`, and
    how many 32-bit C arguments the twin pushes for it.

    Declarative on purpose: the kit half of the door names no game, so a project states its table
    and the kit reads it.

    `takes_image` — argument 0 is the image base, which is true of nearly every core in this
    workspace and is why the door substitutes a HOST pointer for it. A core that touches HARDWARE
    rather than the image has no image to be handed (`hw_bset8(addr, bit)`, `ikbd_send_cmd(cmd)`),
    and substituting a pointer over its first argument would corrupt exactly the value it needs —
    the mirror image of the mistake the substitution's own check exists to catch. Such a core
    declares `takes_image=False` and every argument is read as it stands.

    `returns` — False for a core declared `void`. Its D0 on the machine is whatever the callee
    happened to leave, so the door poisons D0 rather than putting the host's arbitrary return
    register there: a value that is undefined on target must not be a definite number here, or a
    stub that branched on it would pass off target and flake on the machine.
    """

    def __init__(self, name, nargs, takes_image=True, returns=True):
        if takes_image and nargs < 1:
            raise ValueError(f"door callback {name!r} declares {nargs} arguments and takes_image; "
                             f"argument 0 IS the image base, so the count is at least 1")
        if nargs < 0:
            raise ValueError(f"door callback {name!r} declares {nargs} arguments")
        self.name = name
        self.nargs = nargs
        self.takes_image = takes_image
        self.returns = returns


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

    `callbacks` is the project's CALLBACK-DOOR table, `{slot: DoorCallback(...)}`, and `lib` the
    ctypes handle its host cores live in (a project's test code has it as `harness._lib`).

    THE BAND IS ARMED WHETHER OR NOT A TABLE IS GIVEN, and a project with no table is the case that
    makes that matter: its blob may still hold door stubs — one twin gaining one arms nothing by
    itself — and a stub reaching the band with no table would otherwise EXECUTE the zeros there for
    sixteen million instructions and fail as "did not return to the sentinel", naming neither the
    door nor the callee. Armed, it names the slot and says the table is empty.
    """

    def __init__(self, asm_dir, image_size, callbacks=None, lib=None):
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

        self.callbacks = dict(callbacks or {})
        self._hosts = _bind_callbacks(self.callbacks, lib)
        _check_door_band(self.stack_top, self.image_at)

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

        entry = self.entry(symbol)
        seed = [CALLEE_SAVED_SEEDS.get(name, 0) for name in emu.REPORTED_REGS]
        # Held for the whole call: the host pointer handed to a C core is an address INSIDE this
        # view of `mem`, so it must outlive every callback the run makes.
        buf = (ctypes.c_uint8 * len(mem)).from_buffer(mem)
        r = emu.run_bench(mem, entry, arg0=self.image_at, sp=self.stack_top,
                          sentinel=self.sentinel, door=(DOOR_BASE, DOOR_SPAN), seed_regs=seed)
        # THE INSTRUCTION BUDGET IS THE RUN'S, NOT THE SEGMENT'S. `bench_resume` takes a fresh cap
        # per segment, so a twin that keeps re-entering the door — a loop around a core call, a stub
        # reached from the wrong place — would spin forever on segments that each stay under it. A
        # hung suite decides nothing and looks like a broken machine; spending the run's own cap
        # makes it the ordinary "did not return to the sentinel" raise.
        while r["status"] == emu.BENCH_DOOR:
            spent = r["ninsns"]
            self._service_door(mem, buf, emu.bench_door_pc())
            r = emu.bench_resume(entry, max(0, emu.BENCH_MAX_INSNS - spent))
            # ...AND A SEGMENT THAT EXECUTED NOTHING IS A REFUSAL, which the budget alone does not
            # cover: a stub that returns INTO the band puts the PC straight back at a door, so every
            # segment stops after zero instructions, the budget never shrinks and the loop never
            # ends. That is a frame bug in the twin, not a run to keep waiting on.
            if r["status"] == emu.BENCH_DOOR and r["ninsns"] == spent:
                raise AssertionError(
                    f"{symbol} returned from a callback straight back into the door band, at "
                    f"{emu.bench_door_pc():#x}, having executed nothing in between — the stub's "
                    f"frame is wrong, and the run would never end")

        for name, want in CALLEE_SAVED_SEEDS.items():
            got = r["regs"][name]
            if got != want:
                raise AssertionError(
                    f"{symbol} returned with {name} = {got:#x}, not the {want:#x} it was entered "
                    f"with — a callee-saved register its epilogue did not restore. Nothing else "
                    f"here can see that: the image, the return value and the cost are all a "
                    f"correct twin's. Check both `movem` lists and the frame size between them")

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

    def _service_door(self, mem, buf, door_pc):
        """Service ONE callback: call the host C core the stopped-at slot declares, apply its result
        and simulate the stub's `rts` — a plain C call, wreckage of the caller-saved file included
        (see `emu.bench_door_return`)."""
        import emu

        offset = door_pc - DOOR_BASE
        slot, within = divmod(offset, DOOR_STRIDE)
        callback = self.callbacks.get(slot) if not within else None
        if callback is None:
            declared = ", ".join(f"{i} ({cb.name})" for i, cb in sorted(self.callbacks.items()))
            raise KeyError(
                f"a twin jumped to the callback door at {door_pc:#x} — slot {slot}"
                f"{f' + {within}' if within else ''} — which no callback table entry declares. "
                f"What IS declared: {declared or '(nothing)'}. This is a refusal and not a 0: a "
                f"door nobody registered has no host C core behind it, so there is no answer to give")

        sp = emu.bench_door_sp()
        result = self._hosts[slot](*self._door_args(mem, buf, sp, callback))
        emu.bench_door_return(result, *_door_rts(mem, sp), returns=callback.returns)

    def _door_args(self, mem, buf, sp, callback):
        """The callee's C arguments, read off the emulated stack: the return address is AT `sp`, so
        they start at `sp + 4`, one 32-bit word each.

        For a core that takes the image, argument 0 is REPLACED by a host pointer to it inside the
        emulated memory buffer — the core's `uint8_t *image` has to be a real pointer, and the
        emulated base is not one. The emulated value is checked against `image_at` rather than
        discarded: a twin passing anything else has computed the wrong base, and substituting over
        it would hide exactly that. A core declared `takes_image=False` has no such argument, and
        every word is read as it stands.
        """
        stack = [int.from_bytes(mem[sp + 4 + 4 * i:sp + 8 + 4 * i], "big")
                 for i in range(callback.nargs)]
        if not callback.takes_image:
            return stack
        if stack[0] != self.image_at:
            raise AssertionError(
                f"the twin passed {stack[0]:#x} as argument 0 of {callback.name}, not the image "
                f"base {self.image_at:#x} — the door substitutes a host pointer for that argument, "
                f"and would be substituting it over a base the twin got wrong")
        return [ctypes.addressof(buf) + self.image_at] + stack[1:]


def _door_rts(mem, sp):
    """The stub's `rts` as (pc, sp): pop the return address the twin's `bsr` pushed, and drop it."""
    return int.from_bytes(mem[sp:sp + 4], "big"), sp + 4


def _bind_callbacks(callbacks, lib):
    """Resolve every declared callback's host function ONCE, at construction.

    Eagerly, so a table naming a core the candidate `.so` does not export fails where the table is
    written rather than in the middle of a twin run — and so the ctypes signature is set once
    instead of per callback.
    """
    if callbacks and lib is None:
        raise ValueError("a callback table needs the `lib` the host cores live in "
                         "(a project's test code has it as `harness._lib`)")
    hosts = {}
    for slot, callback in callbacks.items():
        if not 0 <= slot < DOOR_SLOTS:
            raise ValueError(f"door slot {slot} ({callback.name}) is outside the band's "
                             f"{DOOR_SLOTS} slots")
        try:
            exported = getattr(lib, callback.name)
        except AttributeError:
            raise AttributeError(f"door slot {slot} declares {callback.name!r}, which the "
                                 f"candidate library does not export") from None
        # A PRIVATE prototype built from the function's ADDRESS, rather than `exported` with its
        # argtypes rewritten. `getattr` on a CDLL hands back a cached object shared with every other
        # user of that library in the process — a project's own tests declare their own signatures
        # for the same cores — and whichever assignment ran last would win.
        #
        # Argument 0 is the host image pointer where the core takes one; the rest are the 32-bit
        # stack words the twin pushed. The result is read as a longword and goes to D0 whole.
        argtypes = [ctypes.c_uint32] * callback.nargs
        if callback.takes_image:
            argtypes[0] = ctypes.c_void_p
        prototype = ctypes.CFUNCTYPE(ctypes.c_uint32, *argtypes)
        hosts[slot] = prototype(ctypes.cast(exported, ctypes.c_void_p).value)
    return hosts


def _check_door_band(stack_top, image_at):
    """The door band must lie in the DEAD GAP between the twin's stack top and the image.

    Asserted rather than assumed: a blob big enough to push the stack into the band, or an image
    small enough to sit under it, would make a door address alias real memory — a twin would write
    where a callback is meant to be caught, or a callback would fire on an ordinary access, and
    neither leaves a trace anything else here could read.
    """
    if not stack_top < DOOR_BASE or not DOOR_BASE + DOOR_SPAN < image_at:
        raise AssertionError(
            f"the callback door band [{DOOR_BASE:#x}, {DOOR_BASE + DOOR_SPAN:#x}) does not lie "
            f"strictly between the twin's stack top ({stack_top:#x}) and the image "
            f"({image_at:#x}) — move DOOR_BASE, because a band that aliases either is undetectable")


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
