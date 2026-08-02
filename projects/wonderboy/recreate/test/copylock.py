"""Get an oracle run past Wonder Boy's Copylock — and prove afterwards that it got past it.

`load_resource_by_index` calls the protection on the FIRST resource load of the boot
(`../notes/architecture.md` §2.5), so every run that crosses the boot path or the resource loader
hits `jsr copylock_entry`. The blob is a Rob Northen trace-decryptor: it decrypts one longword of
itself per single-step exception, so 1,970 of its bytes never exist as plaintext and there is no
source text to port. Running it is not an option either — see test_copylock.py's negative controls,
where an unstubbed run entered at the guard enters the blob and never comes back, and one entered at
an arming site DOES come back, having scrambled 2,053 bytes of the protection on the way.

TWO MECHANISMS, WITH DIFFERENT DOMAINS. That difference is the whole reason this module exists:

  * `Stub.DISARM` pokes `copylock_arm_flag := 0`. It patches no code, and it is the game's own
    steady state — the guard itself does `clr.w copylock_arm_flag` after the first call, so every
    later resource load takes exactly this path. It is valid ONLY for a run that cannot reach an
    arming site: crossing `$e51e` or `$e6dc` re-executes `move.w #$ffff,copylock_arm_flag` and the
    poke is gone before the guard reads it.
  * `Stub.ENTRY_RTS` pokes `rts` over `copylock_entry`. Valid for any run, boot path included,
    because an arming site cannot undo a patch to code it does not write. The `jsr` still executes,
    so the stack behaves as it really would, and nothing between the return and the function's own
    `rts` reads `d0` (`$e7c2` is a `clr.w`) — so returning with an arbitrary `d0` is safe.
    Semantically it is "the protection passed", which is the branch the game takes on a genuine
    disk.

`Stub.BOTH` is the default because choosing between them is a judgement about the run's entry point
that the caller can get wrong silently, and a stub that quietly fails to apply is the exact
false-green class this project spends its effort eliminating. Neither mechanism weakens the other:
under BOTH the guard skips, and if it somehow did not, the entry is an `rts` anyway. There is a
second reason, read out of `recreate_kit/harness.py`'s `_attribution_check`: its poison pass inverts
every byte the oracle wrote below the stack guard, and under DISARM alone the game's own
`clr.w copylock_arm_flag` puts `$e7cc` in that set — so the poisoned re-run would start with the
flag at `$ffff`, RE-ARMED, and walk into the protection. Patching the entry is immune to that by
construction, because nothing writes `copylock_entry`. Ask for a single mechanism when the point is
to DEMONSTRATE its domain (the tests do), or when a run needs the `jsr` itself to execute.

THE WITNESS IS A MEMORY DIFFERENCE, NOT A WRITE SET, and that choice is load-bearing three times
over. `run()` compares the run's final memory against the memory it started from, over the
Copylock's own bytes and the three exception vectors the blob installs:

  * **The write set gives a false positive on the boot path.** At `load_base = 0x3f8` the
    relocator's copy of the program body to `$400` is an IDENTITY copy that writes every byte of the
    image — including all 2,220 bytes of the protection, 96 of them in `copylock_reg_save`. A
    write-set witness reports "the protection DID execute" for a `move.l (a0)+,(a1)+` loop; the
    difference witness reports nothing, because the bytes did not change (measured, both ways).
  * **The write set can silently run out.** `oracle/shim.c`'s `logw()` drops writes past its
    1,048,576-entry ledger without telling anyone, so on a long enough run the blob's own stores
    would simply not be in it. Final memory cannot overflow.
  * **The comparison's baseline is a freshly loaded image**, because `run()` takes POKES rather
    than a caller-built image. A caller cannot hand it memory an earlier run already left the
    protection's effects in — the shape that would put those effects on both sides of the
    comparison and come back green — because there is no parameter to hand it through.

WHAT THE WITNESS GUARANTEES, EXACTLY. The blob's entrance is
`moveq #0,d0 / move.l #$ffffffff,d1 / bra.s $ed46 / move.l a6,-(a7) / lea $ecd4(pc),a6`, and only
then, at `$ed4c`, comes `movem.l d0-a7,(a6)` into `copylock_reg_save` — the FIRST of those six
instructions to write the image at all. The blob loads that `d1` ITSELF, so the four bytes of the
saved `d1` differ from the zero-filled save area whatever registers the caller passed. So the
guarantee is: **the witness fires on any run that COMPLETES that `movem`, and it is independent of
the caller's registers.** It is not "any run that reaches the protection", and the independence is
not free — both halves used to be over-claimed here, and both were demonstrated false:

  * **A run stopped anywhere in the five instructions before the `movem` is invisible**, and so is
    one stopped on the `movem` itself: they write the STACK (`move.l a6,-(a7)`) or nothing at all.
    A `stop_pc` of `$ecca`, `$eccc`, `$ecd2`, `$ed46`, `$ed48` or `$ed4c` reported a run that had
    executed the guard's `jsr` and up to five instructions of the protection as clean. `run()` now
    REFUSES a `stop_pc` inside `[ENTRY, CODE_END)` outright, which is sound because a correctly
    stubbed run cannot reach one.
  * **The caller's POKES used to land on both sides of the comparison.** The blob's whole durable
    memory effect at `REGS_SAVED` is 12 bytes — the saved `d1`, `a0`, `a6` and `a7` — and feeding
    exactly those back through `pokes` came back green with the `movem` executed. `stubbed_image()`
    now REFUSES any poke overlapping `WITNESS_RANGES`. So "independent of its inputs" is true by
    ENFORCEMENT, not by construction.

If a run instead gets far enough to hang or to hit unmodeled hardware, `emu.run` raises and there is
no green result to be wrong about; the two failure modes cover the space between them.

WHAT THE WITNESS'S SOUNDNESS RESTS ON, stated because nothing else states it: **a Rob Northen trace
decryptor is designed to leave no trace.** It decrypts and RE-ENCRYPTS one longword at a time, and it
restores the exception vectors it saved — so a blob that ran to COMPLETION would put the code span
and all three vectors back by construction, and the only evidence left in `WITNESS_RANGES` would be
the 96-byte save area. The witness is sound today only because **the blob cannot complete**: the
kit's Musashi is built with `M68K_EMULATE_TRACE=0` (pinned in `tools/recreate_kit/kit.mk`, not
inherited from the vendored header — see TRAP_MODEL.md), so the single-step exception the decryptor
runs on never fires and an unstubbed run dies executing ciphertext. That flag is load-bearing for
this module. `test_copylock.py` pins it behaviourally.

What the witness does NOT cover, stated because it is the obvious way to lose it: `stub_pokes()` and
`stubbed_image()` are public and unwitnessed, and `recreate_kit.harness.differential()` calls
`emu.run` itself, so a future boot-path differential written as
`differential(entry, regs={"_pokes": copylock.stub_pokes()})` gets no witness at all and must call
`assert_did_not_execute()` by hand. `recreate/STATUS.md` carries that as a knowingly unpinned
surface, with the enabling fix (`differential()` returning its final image) and the reason a per-run
forbidden-WRITE veto in the kit was REJECTED as the fix — it would fire on the relocator's identity
copy, which is the case the difference witness was invented for. Note what that does and does not
rule out: it rules out a WRITE-SET veto, not a difference-based one over project-registered ranges.
Neither is built, and the difference-based one is the same change as returning the final image.
"""
import enum

import harness  # noqa: F401  — binds the kit; `emu` is only importable afterwards
import emu
from layout import wb

RTS = b"\x4e\x75"                                  # 68000 `rts`, the whole of the entry stub
MAX_TRESPASSES_SHOWN = 8                           # addresses listed before the diagnostic elides

ARM_FLAG = wb("COPYLOCK_ARM_FLAG")
ARM_FLAG_LEN = wb("COPYLOCK_ARM_FLAG_LEN")
ARM_INSN_LEN = wb("COPYLOCK_ARM_INSN_LEN")
ARM_SITES = (wb("COPYLOCK_ARM_TITLESCR"), wb("COPYLOCK_ARM_SPRITES"))
DISK_LOAD_FILE = wb("DISK_LOAD_FILE")
GUARD = wb("COPYLOCK_GUARD")
CALL = wb("COPYLOCK_CALL")
SKIPPED = wb("COPYLOCK_SKIPPED")
ENTRY = wb("COPYLOCK_ENTRY")
REG_SAVE = wb("COPYLOCK_REG_SAVE")
REG_SAVE_LEN = wb("COPYLOCK_REG_SAVE_LEN")
REGS_SAVED = wb("COPYLOCK_REGS_SAVED")
DECRYPT_CURSOR = wb("COPYLOCK_DECRYPT_CURSOR")
VECTORS_INSTALLED = wb("COPYLOCK_VECTORS_INSTALLED")
CODE_END = wb("COPYLOCK_CODE_END")
VECTORS = (wb("COPYLOCK_VEC_ILLEGAL"), wb("COPYLOCK_VEC_PRIVILEGE"), wb("COPYLOCK_VEC_TRACE"))
VECTOR_LEN = wb("EXCEPTION_VECTOR_LEN")

DISARMED = bytes(ARM_FLAG_LEN)                     # what `clr.w copylock_arm_flag` leaves
ARMED = b"\xff" * ARM_FLAG_LEN                     # ...and what `move.w #$ffff,...` leaves

# Every byte only the Copylock's own execution changes. The first range covers its code, its 96-byte
# register save area, its decrypt cursor and its ciphertext in one span (they are contiguous); the
# rest are the exception vectors it installs. Nothing else in the image WRITES the vectors — the
# only `move.l <ea>,abs.l` instructions targeting them are the blob's own, at $ed62/$ed6a/$ed80
# (-> $10), $ee14 (-> $20) and $ee0a (-> $24) — and nothing else CHANGES the code span, which is
# what the witness actually tests (test_copylock.py, and the module docstring on why those are
# different questions).
#
# The span starts at ENTRY and so does NOT cover the blob's own four wipe-table pointers immediately
# below it ($ecba..$ecc9, longwords to the four tables at CODE_END). Deliberate, and left as a
# comment rather than closed by widening the span: those 16 bytes are read-only constants, so no run
# can make them differ and widening would add witness that is unpinnable in exactly the way
# REG_SAVE's upper 32 bytes already are (PORTABILITY.md §6.1's knowingly-unpinned list). They are
# equally unpinned in the other direction — nothing proves plaintext code never writes them — which
# is why the limit is stated here rather than argued away.
WITNESS_RANGES = ((ENTRY, CODE_END),) + tuple((v, v + VECTOR_LEN) for v in VECTORS)


class Stub(enum.Flag):
    """Which mechanism(s) to apply. See the module docstring for each one's domain."""
    DISARM = enum.auto()                           # copylock_arm_flag := 0
    ENTRY_RTS = enum.auto()                        # `rts` over copylock_entry
    BOTH = DISARM | ENTRY_RTS


def stub_pokes(mechanism=Stub.BOTH):
    """``{addr: bytes}`` for ``mechanism`` — the two pokes, in the harness's own poke format.

    An empty ``mechanism`` is refused rather than answered with ``{}``: ``enum.Flag`` makes
    ``Stub(0)`` constructible (an ``&``-for-``|`` typo is enough), and a poke dict that stubs
    nothing is indistinguishable from a real one at the call site — a stub that quietly fails to
    apply, which is the thing this module exists to prevent.

    The TYPE is checked for the same reason, and it is the likelier slip: ``mechanism`` is ``run()``
    and ``stubbed_image()``'s second POSITIONAL parameter, so `copylock.run(GUARD, ARMED_POKES)`
    passes a poke dict here. `Stub.DISARM in <dict>` answers False without raising — Python asks the
    right-hand operand — so both branches below would be skipped, `{}` returned, and the run
    reported as stubbed with neither the stub nor the caller's own pokes applied.
    """
    assert isinstance(mechanism, Stub), (
        f"mechanism must be a Stub, not {type(mechanism).__name__} — it is the second POSITIONAL "
        f"parameter, so this is usually a poke dict passed where the mechanism goes; pass it as "
        f"`pokes=`. A non-Stub answers `Stub.DISARM in ...` False and would stub NOTHING silently.")
    assert mechanism, "an empty Stub applies no poke at all; name DISARM, ENTRY_RTS or BOTH"
    pokes = {}
    if Stub.DISARM in mechanism:
        pokes[ARM_FLAG] = DISARMED
    if Stub.ENTRY_RTS in mechanism:
        pokes[ENTRY] = RTS
    return pokes


def _vet_pokes_clear_of_the_witness(pokes):
    """Refuse a caller poke that overlaps ``WITNESS_RANGES``. The inputs half of the guarantee.

    ``pokes`` are written into the image the witness then uses as its own BASELINE, so a poke inside
    the watched span sits on both sides of the comparison and cancels itself out. That is not a
    theoretical shape: the blob's entire durable memory effect at ``REGS_SAVED`` is 12 bytes — the
    saved `d1`, `a0`, `a6` and `a7` — and feeding exactly those back through ``pokes`` returned a
    green run with the `movem` executed (measured, before this guard existed).

    Refused rather than narrowed, because every address in the span is the protection's own storage
    or one of its vectors: a case that wants `copylock_entry` patched asks for ``Stub.ENTRY_RTS``,
    and a case that wants to watch the blob's effects uses ``emu.run`` + ``trespasses()`` the way
    the negative controls do. Neither needs to poke here.

    LIMIT, because it is a guard on ONE door: it sees the pokes that come through ``stubbed_image``,
    not every image the witness is ever shown. ``trespasses()`` and ``assert_did_not_execute()`` are
    public and take two images from anywhere — a caller that builds its own with
    ``harness.make_image`` and then witnesses it gets no vetting at all. That is the same
    "the witness is opt-in at the wrong layer" gap the module docstring closes with.
    """
    for addr, data in pokes.items():
        for lo, hi in WITNESS_RANGES:
            if addr < hi and addr + len(data) > lo:
                raise AssertionError(
                    f"a {len(data)}-byte poke at {addr:#x} overlaps the witness range "
                    f"[{lo:#x},{hi:#x}) — the Copylock's own bytes. `stubbed_image` builds the very "
                    f"image the witness compares AGAINST, so such a poke lands on both sides of the "
                    f"comparison and a run that DID execute the protection would come back clean. "
                    f"To patch {ENTRY:#x}, ask for Stub.ENTRY_RTS; to observe the blob deliberately, "
                    f"use `emu.run` with `trespasses()`.")


def _vet_pokes_clear_of_the_stub(pokes, stub):
    """Refuse a caller poke that OVERLAPS one of the stub's own targets without BEING it.

    An exact address collision is the wanted idiom — a case that arms `copylock_arm_flag` and asks
    for DISARM wants the stub's value at that key — and ``stubbed_image`` gives the stub the last
    word on it. A PARTIAL overlap has no such answer: `{ARM_FLAG - 2: <4 bytes>}` covers the flag
    from a different key, so no merge order can let both pokes mean what they say, and the one that
    loses does so silently. Refuse it and let the caller split the poke.
    """
    for addr, data in pokes.items():
        for stub_addr, stub_data in stub.items():
            if addr != stub_addr and addr < stub_addr + len(stub_data) and addr + len(data) > stub_addr:
                raise AssertionError(
                    f"a {len(data)}-byte poke at {addr:#x} partially overlaps the stub's own "
                    f"{len(stub_data)}-byte poke at {stub_addr:#x}. Whichever is applied second "
                    f"wins, silently — so the run would be reported as stubbed with the stub (or "
                    f"the case's own setup) partly overwritten. Split the poke so it either matches "
                    f"{stub_addr:#x} exactly, in which case the stub wins by design, or clears it.")


def stubbed_image(mechanism=Stub.BOTH, pokes=None):
    """A freshly loaded image with ``pokes`` written in and the stub on top.

    ``pokes`` is for the case's own setup — an armed flag, an `rts` over a hardware-touching call.
    Everything goes through ``harness.make_image``, so the stub faces the kit's poked-input vetting
    like any other poke; Wonder Boy is the project where that block genuinely overlaps the program,
    so a second poke path that skipped it would be a real hole rather than a theoretical one.
    (Pinned: test_copylock.py stages a poke `make_image` refuses and requires it refused HERE.)

    There is deliberately no way to build this on top of an arbitrary caller-supplied image — the
    witness compares a run's memory against what it started from, so an image an earlier run had
    already left the protection's effects in would carry them on both sides and read as clean. That
    argument covers a whole image; it did NOT cover ``pokes``, which was the same hole in miniature,
    so ``_vet_pokes_clear_of_the_witness`` closes it.

    The stub WINS any address collision, which is the point at `copylock_arm_flag` — a case that
    arms the flag and asks for DISARM is asking for exactly this. Note where that property comes
    from, because `{**pokes, **stub}` alone does not carry it: the merge takes the stub's VALUE at a
    shared key but keeps the caller's insertion POSITION, so a later caller key overlapping the stub
    from a *different* address would still be applied over it by `make_image`'s in-order loop.
    `_vet_pokes_clear_of_the_stub` refuses exactly those, which leaves an equal key as the only
    collision reachable — and the merge already resolves that one the right way.
    """
    pokes = pokes or {}
    stub = stub_pokes(mechanism)
    _vet_pokes_clear_of_the_witness(pokes)
    _vet_pokes_clear_of_the_stub(pokes, stub)
    return harness.make_image({**pokes, **stub})


def trespasses(before, after):
    """The Copylock's own bytes that changed between two images — its memory effects, if any."""
    changed = []
    for lo, hi in WITNESS_RANGES:
        if bytes(before[lo:hi]) != bytes(after[lo:hi]):
            changed += [a for a in range(lo, hi) if before[a] != after[a]]
    return changed


def assert_did_not_execute(before, after, entry):
    """Refuse a run that left the protection's effects behind. The reason to use ``run()``."""
    hit = trespasses(before, after)
    if not hit:
        return
    save_area = [a for a in hit if REG_SAVE <= a < REG_SAVE + REG_SAVE_LEN]
    shown = ", ".join(hex(a) for a in hit[:MAX_TRESPASSES_SHOWN])
    raise AssertionError(
        f"the run at {entry:#x} claims to be stubbed, but it changed {len(hit)} byte(s) of the "
        f"Copylock's own storage or of the exception vectors it installs "
        f"({shown}{' ...' if len(hit) > MAX_TRESPASSES_SHOWN else ''}"
        + (f"; {len(save_area)} of them in copylock_reg_save at {REG_SAVE:#x}" if save_area else "")
        + "). So the protection DID execute and this run's memory is whatever a trace-decryptor "
          "left behind, not the game's. The usual cause is Stub.DISARM on a run that crosses an "
          f"arming site ({', '.join(hex(a) for a in ARM_SITES)}), which re-arms the flag before the "
          f"guard at {GUARD:#x} reads it; Stub.ENTRY_RTS survives that.")


def _vet_stop_pc_clear_of_the_blob(stop_pc):
    """Refuse a checkpoint inside the protection. The other half of the guarantee.

    The witness's earliest evidence is the `movem.l d0-a7,(a6)` that completes at ``REGS_SAVED``;
    the five instructions before it write the STACK or nothing at all. So a checkpoint at any of
    those five — or at the `movem` itself, which has not retired yet — stops the run in a window
    where the witness has nothing to see, and the run is reported clean having executed the guard's
    `jsr` and up to five instructions of the protection (measured, before this guard existed).

    The whole span is refused rather than just that window, because a correctly stubbed run never
    enters the blob at all: any checkpoint inside it is unreachable, so refusing it costs a caller
    nothing it could legitimately have wanted.

    Raised rather than ``assert``ed: the module docstring states this refusal as an unconditional
    property, and a bare assert is not one — `python -O` would drop it and hand back the demonstrated
    false negative with every other check in this module still working.
    """
    if ENTRY <= stop_pc < CODE_END:
        raise AssertionError(
            f"stop_pc {stop_pc:#x} is inside the protection itself ([{ENTRY:#x},{CODE_END:#x})). A "
            f"correctly stubbed run never enters the blob, so that checkpoint is unreachable; and a "
            f"run that DID enter it can be stopped in the six instructions up to and including the "
            f"`movem.l d0-a7,(a6)` that completes at {REGS_SAVED:#x}, where the witness still has "
            f"nothing to see and would report the run clean. Stop at {SKIPPED:#x} (the guard's far "
            f"side) instead, or — to observe the blob deliberately — use `emu.run` with "
            f"`trespasses()`.")


def run(entry, mechanism=Stub.BOTH, pokes=None, **kwargs):
    """``emu.run`` with the Copylock stubbed, refusing any result the witness contradicts.

    ``kwargs`` go straight to ``emu.run`` (``regs``, ``stop_pc``, ``max_insns``). There is
    deliberately no way to get a run out of THIS function without the witness; the module docstring
    says what that does and does not cover, and the two guards it calls first are what make its
    guarantee independent of the caller's inputs.
    """
    _vet_stop_pc_clear_of_the_blob(kwargs.get("stop_pc", 0))
    before = stubbed_image(mechanism, pokes)
    after, writes, out = emu.run(before, entry, **kwargs)
    assert_did_not_execute(before, after, entry)
    return after, writes, out
