"""Shared driver for the game's LEAF routines — the ones with no callee, no hardware and a write
set small enough to name.

`test_effects.py`, `test_hud.py`, `test_input.py`, `test_scroll.py`, `test_actor.py`, `test_map.py`
and `test_text.py` are all batteries of such functions, so what they would otherwise each restate
lives here: where a function starts (looked up in `../names.txt`, the workspace's source of truth for
names, rather than restated as a number), what counts as a write it was not entitled to make, the
operand encodings a battery pins its entry points against, how a case seeds an image it can tell
apart afterwards, and how it reads a value back out of the oracle's write set.

NOT a general harness — the kit is that. This module assumes what a leaf gives it: a run short
enough for a tight instruction cap, and a write set the caller can enumerate up front.
"""
import contextlib
import ctypes
import zlib

import harness
from harness import differential, report

import emu                                                       # noqa: E402

# The straight-line leaves are 8 to 38 bytes long and execute at most six instructions. The cap is
# deliberately far below the kit's default: a case that entered the wrong address and ran off into
# the game would otherwise return a plausible-looking result instead of failing. A battery whose
# routines LOOP (the panel blits move up to 32 rows) passes `run(..., max_insns=)` with its own cap,
# derived from that routine's own geometry for the same reason.
LEAF_INSN_CAP = 64

# `osh_run` counts ONE instruction past the routine's own `rts` — the sentinel it returns to — so a
# cap of exactly the body's instruction count reports "did not reach rts". It is a property of THE
# RUNNER, not of any routine, which is why it lives here rather than in whichever battery measured
# it first (test_sound.py did); three batteries now derive their caps from instruction counts and
# would otherwise each absorb it as unexplained slack.
RUNNER_SENTINEL_INSN = 1

# The YM2149's two ports, as the 68000 addresses them. The data port is spelt as an OFFSET from the
# select latch rather than as a literal of its own — the ST decodes the chip incompletely and
# test_audio_capture.py names its odd alias at +1 the same way, so the three cannot drift apart.
# shim.c holds the same pair (`PSG_SELECT`/`PSG_DATA`); the differential is what pins them equal.
PSG_SELECT = 0xff8800
PSG_DATA = PSG_SELECT + 2

# The FOUR hardware bytes the kit's SEEDED READ model serves (TRAP_MODEL.md, "Phase 7"), as the
# 24-bit bus addresses the game's own operands carry — $17c7e reads the first and $17c90 the second
# (`btst`s in the tempo head), $51ae and $51b6 the video counter's mid and low bytes, and $68d0 that
# low byte again in the PRNG. Spelt here rather than unpacked from `emu.HW_ADDRS` because they are a
# fact about the GAME's operands, which the disassembly can be checked against, and because
# unpacking would silently assume which slot is which; test_sound.py pins the whole tuple equal to
# the model's own table, so a slot renumbered in os.h cannot leave a battery declaring an address
# the model no longer names. test_audio_capture.py reads them from here for PSG_SELECT's reason.
MFP_GPIP = 0xfffa01
SHIFTER_SYNC = 0xff820a
VIDEO_COUNTER_MID = 0xff8207
VIDEO_COUNTER_LOW = 0xff8209
MODELED_HW_ADDRS = (MFP_GPIP, SHIFTER_SYNC, VIDEO_COUNTER_MID, VIDEO_COUNTER_LOW)


def hw_declared(video=0x00):
    """The ``hw_seed`` every run that reaches the game's two PRNGs must pass.

    `rng_next` ($68c6) and `rng_1_to_4_masked` ($51ac) READ the video counter, and an undeclared
    modeled read refuses the differential — so a battery that reaches either declares what the
    counter held. It lives here rather than in test_rng.py because it is a fact about the KIT's
    model, and three batteries were importing it from a sibling battery to get at it.

    The default is the byte the model used to FABRICATE, so a case that only wants the declaration
    keeps the numbers it had; a case that wants the entropy live passes its own.
    """
    return {VIDEO_COUNTER_MID: video, VIDEO_COUNTER_LOW: video}

# The game's own two screen buffers (../names.txt: screen_back starts at $70000, screen_front
# $78000, and clear_both_screens clears $70000..$7fd00 — exactly the two back to back). Every
# battery whose routines DRAW takes its destination from one of them, because a destination comes
# out of memory and nothing may be hardcoded; it lives here rather than in one of them because two
# files would otherwise carry the same pair and could disagree about it.
SCREEN_BUFFERS = (0x70000, 0x78000)

# Every address in ../names.txt that carries a name, inverted. Two functions sharing a name would
# make `entry_of` ambiguous, so the inversion is checked rather than assumed.
_ADDRS_BY_NAME = {}
for _addr, _name in harness.NAME_MAP.items():
    _ADDRS_BY_NAME.setdefault(_name, []).append(_addr)


def entry_of(name):
    """The runtime address ``../names.txt`` gives ``name``.

    The tests take entry points from the name map rather than from a table of their own, so a
    function that moves or is renamed there fails as a missing name at collection time instead of
    running the oracle at a stale address. The map is only half the pin: each battery also compares
    the bytes AT the address against the instruction it believes is there.
    """
    addrs = _ADDRS_BY_NAME.get(name, [])
    assert len(addrs) == 1, (
        f"{name!r} names {len(addrs)} address(es) in {harness.NAMES} ({[hex(a) for a in addrs]}) — "
        f"a leaf case needs exactly one entry point")
    return addrs[0]


def bind(name, argtypes, restype=None):
    """Bind one candidate symbol's ctypes signature and return it."""
    fn = getattr(harness._lib, name)
    fn.argtypes = argtypes
    fn.restype = restype
    return fn


IMAGE_ARG = [ctypes.POINTER(ctypes.c_uint8)]


def image_glue(name, restype=None):
    """Differential glue for a reconstruction whose only argument is the image.

    The kit calls glue as ``glue(lib, image)`` and most leaves take the image and nothing else, so
    binding one is the same line every time. The bound symbol is captured by this call rather than
    by a comprehension's loop variable, which is the idiom this replaces.

    ``restype`` is for the ones that also hand a REGISTER back — `hud_blit_panel_frame` leaves the
    d0 its caller spends as a font select — so a case can compare ``info["ret"]`` against the
    oracle's own register without the glue being hand-rolled. (test_scroll.py's returning routines
    are NOT these: each of its steps records what came back into a list the case reads afterwards,
    so their glue does more than call and return and stays hand-written.)
    """
    fn = bind(name, IMAGE_ARG, restype)
    return lambda _lib, image: fn(image)


def register_glue(name, argtypes, restype=None):
    """Glue factory for a leaf whose ENTRY REGISTERS are its arguments.

    ``image_glue`` covers the routines that take only the image. These take the image plus the 68000
    registers the original is entered with — a source pointer in a0, a packed-BCD addend in d0 — so
    the symbol is bound once and each case supplies its own register values:

        blit = leaf.register_glue("hud_blit_cell_or", [ctypes.c_uint32] * 2)
        leaf.run("hud_blit_cell_or", blit(source, destination), ...)

    The C takes one ``uint32_t`` per register whatever operand size the original uses, so the
    truncation the original does (`move.w d0,...` on a longword register) happens in the
    reconstruction where a case can pin it, and not in the glue where it could not.
    """
    fn = bind(name, IMAGE_ARG + list(argtypes), restype)

    def with_registers(*values):
        return lambda _lib, image: fn(image, *values)

    return with_registers


def on_machine_stack(addr):
    """Whether ``addr`` is inside the band the run's own call frames occupy.

    The oracle enters with A7 at ``emu.STACK_TOP`` and the stack grows DOWN, so the band is bounded
    on BOTH sides: a write at or above STACK_TOP is not a call frame however close to the stack it
    looks — the longword AT STACK_TOP is the return address the runner planted, which a routine that
    rewrites it (`addq.l #4,(a7)`) is being watched for rather than excused for.
    """
    return emu.STACK_TOP - emu.STACK_SCRATCH <= addr < emu.STACK_TOP


def stray_writes(writes, allowed):
    """Oracle writes outside ``allowed`` (an iterable of (addr, length) the function may touch).

    The machine stack is the one implicit permission, per ``on_machine_stack``. (test_rad_depack.py
    calls this as well; STATUS.md registers the family and the kit as its proper home.)
    """
    def permitted(addr):
        if on_machine_stack(addr):
            return True
        return any(lo <= addr < lo + length for lo, length in allowed)

    return sorted(a for a in writes if not permitted(a))


def program_writes(info):
    """The oracle's write set with the MACHINE STACK left out.

    A `bsr`'s pushed return address is not program output, and a battery that states its write set
    EXACTLY compares against a model of what the routine draws. The band is `on_machine_stack`'s,
    the same one `stray_writes` permits; this is the other side of it, for the cases that state the
    write set rather than bound it. Its upper bound EXCLUDES the return slot at STACK_TOP, which IS
    program output: it is what a scroll step rewrites to consume its caller's `bsr`.
    """
    return {addr: value for addr, value in info["writes"].items() if not on_machine_stack(addr)}


def merge_bands(addresses):
    """Adjacent addresses collapsed into (start, length) bands, for `run`'s `allowed`."""
    bands = []
    for addr in sorted(addresses):
        if bands and addr == bands[-1][0] + bands[-1][1]:
            bands[-1] = (bands[-1][0], bands[-1][1] + 1)
        else:
            bands.append((addr, 1))
    return bands


def run(name, glue, allowed, what, regs=None, poison=True, max_insns=LEAF_INSN_CAP, stop_pc=0,
        psg_seed=None, hw_seed=None):
    """Run ``name``'s original under the oracle and the reconstruction on the same image.

    Requires the two to agree byte for byte over the whole image, and the original to have written
    nothing outside ``allowed``. Returns the differential's ``info`` so a caller can also assert on
    the returned d0. ``poison`` runs the kit's attribution pass, which is what stops a case passing
    because the destination already held the value the function writes; a caller turns it off only
    when inverting an output would corrupt an ADDRESS the run then stores through. ``max_insns``
    raises the cap for a routine that loops — state the number the routine's own geometry gives, so
    it stays a cap and not a formality.

    ``stop_pc`` is the kit's second stop condition, and TWO families of routine need it.

      * A routine that returns to the WRONG PLACE. The scroll steps ADD to their own return address
        (`addq.l #4,(a7)`) to skip the caller's next `bsr`, so their `rts` lands past the oracle's
        sentinel and the run would otherwise never stop. A case passes the sentinel plus that skip
        distance and both arms then terminate — see test_scroll.py, which also reads the decision
        back out of the write set rather than inferring it from this.
      * A routine that TRANSFERS to a tail the reconstruction declines to follow. The scene driver's
        exits `bra`/`jmp` into two routines that end in an unverifiable `jsr`, so the C returns WHICH
        tail it reached and the case sets ``stop_pc`` to that tail's address, diffing the whole
        prefix at the instant control arrives there — see test_scene.py.

    THE SECOND FAMILY OWES A WITNESS. A checkpointed run stops at EITHER the checkpoint or the
    `rts`, and emu.run reports only that one of them was reached — so a case that merely set
    ``stop_pc`` would pass whether or not the tail was taken. Such a case must carry its own
    POSITIVE evidence of which stop fired: ``run_reaching`` below is that witness.

    ``psg_seed`` is ``{register: byte}``, the contents the case declares the YM2149 held on ENTRY —
    the direct ``$ff8800``/``$ff8802`` path's off-image register file, seeded identically into both
    cores (tools/recreate_kit/TRAP_MODEL.md, "Phase 6"). A routine that READS a register back has to
    have it declared or the oracle refuses the whole run, because the bits it preserves are an input
    and inventing them is a false green: `snd_psg_silence`'s `ori.b #$3f` over the mixer is this
    project's case, and test_sound.py holds it. Seed or none, the harness compares both sides' access
    ledger and register file afterwards — neither is in the image, so nothing else could.

    ``hw_seed`` is ``{address: byte}`` over the modeled hardware set (``MODELED_HW_ADDRS`` above),
    the bytes the case declares those addresses held on ENTRY, seeded identically into both cores
    (TRAP_MODEL.md, "Phase 7"). Same rule as ``psg_seed`` and a sharper one, in two shapes. The two
    STATIC bytes steer a BRANCH: an undeclared read is not merely uncompared — both cores are served
    a fabricated 0, take the same wrong arm, and agree (`snd_music_tick`'s tempo selector, in
    test_sound.py). The two VIDEO-COUNTER bytes are summed into an ARITHMETIC result instead, which
    is the same false green with a wider blast radius: a fabricated 0 collapses the game's PRNG to a
    constant both cores then agree on (`rng_next`, in test_rng.py — use ``hw_declared()``). Those
    two are also VOLATILE: the machine changes them on its own, so a run may read each ONCE and a
    second read is its own refusal. The refusal differs from the PSG model's in WHERE it fires: an undeclared
    PSG read sinks `emu.run` itself, while an undeclared hardware read is served and recorded and
    only ``differential`` refuses — so this one surfaces as an AssertionError, not a RuntimeError.
    Both sides' ordered read stream and declared-byte file are compared afterwards; neither is in the
    image, so a port that skipped a read or read the WRONG modeled address has no other surface.
    """
    diffs, info = differential(entry_of(name), dict(regs or {}), glue,
                               max_insns=max_insns, poison=poison, stop_pc=stop_pc,
                               psg_seed=psg_seed, hw_seed=hw_seed)
    assert not diffs, f"{what}\n{report(diffs)}"
    stray = stray_writes(info["writes"], allowed)
    assert not stray, (
        f"{what}: {len(stray)} write(s) outside {[(hex(a), n) for a, n in allowed]}, e.g. "
        f"{harness.label(stray[0])} @ {stray[0]:#x}")
    return info


@contextlib.contextmanager
def pc_coverage():
    """The oracle's executed-PC tracking, armed for the block and disarmed afterwards.

    The bitset is GLOBAL and accumulates across runs, so a caller that wants to ask about ONE run
    has to reset it first and stop tracking after — three lines that were spelt twice here
    (test_scene.py's `run_reaching`, test_copylock.py's `_run_reaching`) before a third user asked
    for them. The reset DESTROYS any corpus being accumulated, which is the caveat both copies
    carried; no battery here accumulates one.
    """
    emu.cov_enable()
    emu.cov_reset()
    try:
        yield
    finally:
        emu.cov_enable(False)


def run_reaching(name, glue, allowed, what, transfer, **kwargs):
    """``run``, plus the witness that a checkpointed run really did take its tail: the TRANSFER
    INSTRUCTION at ``transfer`` executed.

    A ``stop_pc`` run stops at EITHER the checkpoint or the `rts`, and emu.run reports only that one
    of them was reached — so a case that merely set a checkpoint would pass whether or not the tail
    was taken. The oracle marks each PC as it executes it and stops BEFORE marking the checkpoint, so
    "the `bra`/`ble` into the tail ran" is exactly the missing fact, and it names WHICH transfer
    fired rather than only that something did.

    THIS BELONGS IN THE KIT. The shim already knows which of its two stops fired (`final_pc`) and
    reporting it would make the witness exact and free. It lives here instead because two batteries
    (test_scene.py, test_actor.py) need it and neither may own it; test_copylock.py is the third
    coverage user and shares `pc_coverage` above rather than this, since it drives its own runner and
    ASKS whether the witness fired instead of requiring it.
    """
    with pc_coverage():
        info = run(name, glue, allowed, what, **kwargs)
    assert emu.cov_visited(transfer), (
        f"{what}: the run reached its checkpoint without executing the transfer at {transfer:#x}, "
        f"so it RETURNED rather than taking the tail this case is about")
    return info


# --- building an entry pin -----------------------------------------------------------------------
# The operand encoders, the branch displacements and the opcodes MORE THAN ONE battery spells. A
# battery keeps its own single-use encodings next to the routines that need them; these are here
# because two files would otherwise carry the same four bytes and could disagree about them.
#
# Both encoders MASK to their width, which is the 68000's own behaviour: an operand field holds
# exactly two or four bytes, so a caller passing a negative displacement (`word(-18)` for a `dbf`) or
# a value with rubbish above the field gets what the instruction stream would hold. Without the mask
# `to_bytes` would raise OverflowError on the negative case and hide the readable failure.
WORD_MASK = 0xffff
LONGWORD_MASK = 0xffffffff

RTS = b"\x4e\x75"
BSR_W = b"\x61\x00"                 # bsr.w <d16>
MOVE_W_ABS_L_D0 = b"\x30\x39"       # move.w <abs>.l,d0
MOVE_W_D0_ABS_L = b"\x33\xc0"       # move.w d0,<abs>.l
MOVE_W_ABS_L_ABS_L = b"\x33\xf9"    # move.w <abs>.l,<abs>.l
MOVE_W_IMM_ABS_L = b"\x33\xfc"      # move.w #imm,<abs>.l


def word(value):
    return (value & WORD_MASK).to_bytes(2, "big")


def longword(value):
    return (value & LONGWORD_MASK).to_bytes(4, "big")


def opcode(value):
    """One 68000 opcode word, as the two bytes the instruction stream holds.

    Every battery that builds its pins from numbers rather than from byte literals spells this;
    it is here so the three of them cannot disagree about the width or the byte order.
    """
    return value.to_bytes(2, "big")


def lea_abs_l(reg, addr):
    """`lea <abs>.l,An` — how every one of these routines names a global."""
    return opcode(0x41f9 | (reg << 9)) + longword(addr)


def lea_d16(reg, displacement, source=None):
    """`lea d16(As),Ad` — how every one of them steps a cursor.

    Usually one register advancing itself, so the source defaults to it. The scroll's pre-shift is
    the exception: it steps from one buffer copy to the next by `lea $5800(a0),a1`.
    """
    return opcode(0x41e8 | (reg << 9) | (reg if source is None else source)) + word(displacement)


def movea_l_abs_w(reg, addr):
    """`movea.l <abs>.w,An` — how a routine loads a pointer held BELOW $8000 (WB_SCREEN_BACK is,
    so the scroll's blit and the message box's both name it short)."""
    return opcode(0x2078 | (reg << 9)) + word(addr)


def movea_l_abs_l(reg, addr):
    """`movea.l <abs>.l,An` — the long form, for a pointer held at or above $8000. FOUR batteries
    spelt this (test_actor.py, test_scroll.py, test_map.py, test_stage.py), which is the most any
    encoding here was duplicated."""
    return opcode(0x2079 | (reg << 9)) + longword(addr)


def move_l_imm_abs_l(value, addr):
    """`move.l #imm,<abs>.l` — how a routine plants a whole pointer, and how $fb06 plants all
    sixteen of the scroll engine's buffer row cursors."""
    return opcode(0x23fc) + longword(value) + longword(addr)


# `jsr <abs>.l` — a call that names its callee by ADDRESS rather than by displacement, so unlike
# `bsr_w` it assembles the same wherever it sits. The opcode word is exported as well as the
# assembled form because two batteries only ever compare against it: test_map.py and test_actor.py
# scan the program for calls rather than building one.
JSR_ABS_L = 0x4eb9


def jsr_abs_l(addr):
    """`jsr <abs>.l`. FOUR batteries (test_copylock.py's stub call, test_hud.py's one non-`bsr` call
    in the panel pass, and test_map.py's and test_actor.py's call scans, which use the opcode word
    above on its own)."""
    return opcode(JSR_ABS_L) + longword(addr)


# The 68000's BRIEF EXTENSION WORD, which every indexed operand in this reconstruction carries and
# which three encoders below plus test_sound.py's own spelt inline until they met here: the index
# REGISTER at bits 15-12, bit 15 choosing An over Dn, the WORD/LONG bit at 11, and an 8-bit
# displacement. Getting any of those fields wrong assembles a different instruction that still looks
# right, which is why one spelling matters more here than the line count suggests.
INDEX_IS_ADDRESS_REGISTER = 0x8000
INDEX_IS_LONGWORD = 0x800
DISPLACEMENT_MASK = 0xff


def brief_extension_word(register, displacement=0, longword_index=False, address_register=False):
    """One indexed operand's extension word. The displacement is masked to its byte because that is
    the field's width, exactly as `word()` masks a displacement to two."""
    return word((INDEX_IS_ADDRESS_REGISTER if address_register else 0) | (register << 12)
                | (INDEX_IS_LONGWORD if longword_index else 0)
                | (displacement & DISPLACEMENT_MASK))


def lea_indexed(reg, index, displacement=0, longword_index=False, source=None):
    """`lea d8(As,Dn.w),Ad` — the extension word above is the whole of the index encoding.

    ONE spelling for what test_scroll.py and test_text.py each had half of: the scroll needs the
    LONGWORD index bit (a tile offset it has already shifted into the high half) and the text plotter
    and the map probes need the 8-bit DISPLACEMENT.

    ``source`` defaults to the destination, which is what every caller but one wants; $f95c's
    `lea 0(a1,d0.w),a0` indexes the palette table in a1 into a0, so the base is separable here for
    `lea_d16`'s reason rather than being a second encoder.
    """
    return opcode(0x41f0 | (reg << 9) | (reg if source is None else source)) + brief_extension_word(
        index, displacement, longword_index)


def move_w_ind_dn(reg, base, displacement=0):
    """`move.w (An),Dn` and its `d16(An)` form — how every one of these routines reads a field."""
    if displacement == 0:
        return opcode(0x3010 | (reg << 9) | base)
    return opcode(0x3028 | (reg << 9) | base) + word(displacement)


def move_w_postinc_dn(reg, base):
    """`move.w (An)+,Dn` — how every one of these routines walks a word cursor. The base register is
    always spelt out: test_scroll.py's own copy took it as read (it only ever steps a0), which is a
    constant hidden in an encoder rather than in the call that knows it."""
    return opcode(0x3018 | (reg << 9) | base)


def move_b_d16_dn(reg, base, displacement):
    """`move.b d16(An),Dn` — how the collision probes read a map byte out of a record."""
    return opcode(0x1028 | (reg << 9) | base) + word(displacement)


def tst_b_d16(base, displacement):
    """`tst.b d16(An)` — how a routine tests a BYTE FIELD of a record it holds a pointer to. THREE
    batteries spelt it (test_actor.py's spawn countdown, test_hud.py's slot request as a byte
    literal, test_sound.py's SFX flags through the module base in a3), which is the count that moves
    an encoding here."""
    return opcode(0x4a28 | base) + word(displacement)


def move_b_postinc_dn(reg, base):
    """`move.b (An)+,Dn` — how a routine walks a BYTE cursor, and the sibling of
    `move_w_postinc_dn` above. Its base register is spelt out for that one's reason: test_scroll.py
    and test_text.py each carry a `0x101e` byte literal with the register pair taken as read, which
    is a constant hidden in a name rather than in a call. TWO batteries spell the generic form
    (test_stage.py, test_sound.py) and those two are converted; the fixed-register pair is noted here
    rather than rewritten, since converting them is a change to those batteries' style."""
    return opcode(0x1018 | (reg << 9) | base)


def move_w_indexed_dn(reg, base, index, displacement=0, longword_index=False):
    """`move.w d8(An,Dm.?),Dn` — how a routine reads a word out of a table it has just indexed.

    THREE batteries import this: test_scroll.py's fills (which spelt it `move_w_indexed_d0`, base
    only), test_stage.py's index-table lookup, and test_actor.py's damage lookup, which is the one
    that needs the other two fields — its two reads differ in exactly the extension word's LONGWORD
    bit. Same argument order as `lea_indexed` above, with the base register split out because it is
    not the destination here.
    """
    return opcode(0x3030 | (reg << 9) | base) + brief_extension_word(
        index, displacement, longword_index)


def move_w_imm_abs_l(value, addr):
    """`move.w #imm,<abs>.l` — the whole instruction behind `MOVE_W_IMM_ABS_L`. THREE batteries
    import this (test_text.py, test_stage.py, test_actor.py), which spelt it under one name and two
    different bodies — test_stage.py's built the opcode word from an integer where the other two
    took it from the constant above."""
    return MOVE_W_IMM_ABS_L + word(value) + longword(addr)


def move_w_imm_abs_w(value, addr):
    """...and the SHORT form, for a destination below $8000. TWO batteries (test_stage.py's
    new-game reset, test_scene.py's exit action)."""
    return opcode(0x31fc) + word(value) + word(addr)


def move_w_abs_l_dn(reg, addr):
    return opcode(0x3039 | (reg << 9)) + longword(addr)


def move_b_abs_l_dn(reg, addr):
    """`move.b <abs>.l,Dn` — how a routine reads a hardware port (the PSG read-back, an MFP byte)."""
    return opcode(0x1039 | (reg << 9)) + longword(addr)


def move_b_dn_abs_l(reg, addr):
    """`move.b Dn,<abs>.l` — the SOURCE register sits in the low three bits (a `move`'s source EA)
    where a destination's sit at 11-9. TWO batteries: test_sound.py's PSG data write and
    test_stage.py's tune latch."""
    return opcode(0x13c0 | reg) + longword(addr)


def move_b_imm_abs_l(value, addr):
    """`move.b #imm,<abs>.l` — the immediate occupies a WORD in the stream even for a byte move, so
    the byte travels in its low half."""
    return opcode(0x13fc) + word(value & 0xff) + longword(addr)


def move_b_imm_d16(base, value, displacement):
    """`move.b #imm,d16(An)` — the same immediate-in-a-word rule against a based operand. THREE
    batteries (test_actor.py's launch speed, test_map.py's stamped tile, test_sound.py's active
    flag, which reaches its field through the module base in a3)."""
    return opcode(0x117c | (base << 9)) + word(value & 0xff) + word(displacement)


def tst_w_abs_w(addr):
    """`tst.w <abs>.w` — the mode flags and the scroll's gate are all below $8000, so the original
    spells them short."""
    return opcode(0x4a78) + word(addr)


def subi_w_dn(reg, value):
    return opcode(0x0440 | reg) + word(value)


def subq_w_dn(amount, reg):
    """`subq.w #n,Dn` — a 3-bit count, so it is masked like the shifts'. THREE batteries
    (test_map.py's step counters, test_scroll.py's queue walk, test_hud.py's meter charge), which
    spelt it under three names and two argument orders until they met here."""
    return opcode(0x5140 | ((amount & 7) << 9) | reg)


def addi_w_dn(reg, value):
    """`addi.w #imm,Dn`. THREE batteries (test_scroll.py, test_map.py, test_actor.py)."""
    return opcode(0x0640 | reg) + word(value)


def andi_w_dn(reg, value):
    """`andi.w #imm,Dn` — how a routine masks a register down to a field. THREE batteries
    (test_scroll.py's phase and tile-row masks, test_map.py's cell mask, test_blit.py's two masks
    that split the screen x)."""
    return opcode(0x0240 | reg) + word(value)


def tst_w_dn(reg):
    """`tst.w Dn`. THREE batteries (test_scroll.py, test_map.py, test_hud.py)."""
    return opcode(0x4a40 | reg)


def btst_imm_dn(bit, reg):
    """`btst #n,Dn` — a LONGWORD test, unlike the byte one `bit_op_d16` assembles against memory.
    THREE batteries (test_stage.py, test_text.py, test_actor.py)."""
    return opcode(0x0800 | reg) + word(bit)


def move_l_imm_postinc(reg, value):
    """`move.l #imm,(An)+`. THREE batteries (test_actor.py, test_stage.py, test_hud.py)."""
    return opcode(0x20fc | (reg << 9)) + longword(value)


def cmpi_w_d16(base, value, displacement):
    """`cmpi.w #imm,d16(An)` — how a routine tests a WORD FIELD of a record against a constant.
    THREE batteries (test_actor.py's and test_map.py's, which spelt it identically, and
    test_scene.py's shop counts). It is also the instruction the $dcd4/$dd42 slip was meant to be,
    which is why that pin spells this one beside `cmpi_w_abs_l` below."""
    return opcode(0x0c68 | base) + word(value) + word(displacement)


def cmpi_w_abs_l(value, addr):
    """`cmpi.w #imm,<abs>.l` — the same test against a GLOBAL. TWO batteries (test_scroll.py and
    test_scene.py); test_hud.py spells the opcode word alone as `CMPI_W_IMM_ABS_L` and composes the
    rest itself, so it is a third half-user rather than a fourth."""
    return opcode(0x0c79) + word(value) + longword(addr)


def sub_w_dn_d16(reg, base, displacement):
    """`sub.w Dn,d16(An)` — a word subtracted straight off a record field, leaving the BORROW in N.
    TWO batteries: test_actor.py's template hit-point pool and test_scene.py's visit budget."""
    return opcode(0x9168 | (reg << 9) | base) + word(displacement)


def cmpi_b_dn(reg, value):
    """`cmpi.b #imm,Dn` — the immediate is a WORD in the stream even for a byte compare."""
    return opcode(0x0c00 | reg) + word(value)


def sub_w_dn_dn(destination, source):
    return opcode(0x9040 | (destination << 9) | source)


def add_w_dn_dn(destination, source):
    return opcode(0xd040 | (destination << 9) | source)


def cmp_w_imm_dn(reg, value):
    """`cmp.w #imm,Dn` — CMP with an IMMEDIATE source EA, which is a different instruction from
    `cmpi.w #imm,Dn` meaning the same thing; both appear in this image. THREE batteries
    (test_blit.py's clip thresholds, test_actor.py's, test_rng.py's BCD ladder), which spelt it
    identically under one name."""
    return opcode(0xb07c | (reg << 9)) + word(value)


def cmp_w_dn_dn(destination, source):
    """`cmp.w Dn,Dn` — a SIGNED compare of two registers. THREE batteries (test_actor.py's reach
    tests, test_map.py's sub-cell tests, test_blit.py's bottom clamp)."""
    return opcode(0xb040 | (destination << 9) | source)


def move_w_dn_dn(destination, source):
    return opcode(0x3000 | (destination << 9) | source)


def move_w_imm_dn(reg, value):
    return opcode(0x303c | (reg << 9)) + word(value)


def moveq(value, reg):
    """`moveq #n,Dn` — an 8-bit immediate SIGN-EXTENDED into the whole longword register, which is
    why the immediate is masked to a byte rather than checked against the register's width."""
    return opcode(0x7000 | (reg << 9) | (value & 0xff))


def moveq_0_dn(reg):
    """`moveq #0,Dn`, the one immediate the walks in test_actor.py and test_map.py ever use — spelt
    for it because "clear the register before a word load" is what those sites mean."""
    return moveq(0, reg)


def clr_w_dn(reg):
    """`clr.w Dn` — a WORD clear, so the caller's high half survives it. THREE batteries
    (test_actor.py, test_map.py, test_blit.py)."""
    return opcode(0x4240 | reg)


def swap_dn(reg):
    """`swap Dn` — how a routine gets at the half of a longword register a rotate pushed up. THREE
    batteries (test_scroll.py's tile loop and its pre-shift, test_stage.py's derived copies,
    test_blit.py's every column seam), which is why it moved here. The register field is masked to
    three bits like its neighbours': without it a register out of range would silently encode a
    different instruction (`bkpt`) rather than fail."""
    return opcode(0x4840 | (reg & 7))


def mulu_w_imm_dn(reg, value):
    return opcode(0xc0fc | (reg << 9)) + word(value)


def lsl_w_imm_dn(count, reg):
    """`lsl.w #n,Dn` — a count of 8 is encoded as 0, which is why the field is masked to three bits."""
    return opcode(0xe148 | ((count & 7) << 9) | reg)


# `asr.w #n,Dn` and `asl.w #n,Dn`: one base opcode and the DIRECTION bit that separates them. The
# pair is stated once because a battery that spells both (the sprite pass does) would otherwise be
# able to get them the wrong way round and still assemble.
_ASHIFT_W_IMM = 0xe040
_ASHIFT_LEFT = 0x100


def asr_w_imm_dn(count, reg):
    """`asr.w #n,Dn` — an ARITHMETIC shift, so a negative word stays negative. THREE batteries
    (test_actor.py, test_map.py, test_blit.py). test_actor.py's own copy `or`ed in a redundant
    `1 << 6` over a base that already carries bit 6; all three emitted the same bytes, which is what
    their entry pins were agreeing about."""
    return opcode(_ASHIFT_W_IMM | ((count & 7) << 9) | reg)


def asl_w_imm_dn(count, reg):
    """...and the left one, which only test_blit.py's sprite pass spells. It lives beside its twin
    rather than in that battery because the base opcode above must be a single statement."""
    return opcode(_ASHIFT_W_IMM | _ASHIFT_LEFT | ((count & 7) << 9) | reg)


def tst_b_abs_l(addr):
    return opcode(0x4a39) + longword(addr)


def tst_w_abs_l(addr):
    return opcode(0x4a79) + longword(addr)


def clr_w_d16(base, displacement):
    """`clr.w d16(An)` — how a routine zeroes a WORD field of a record it holds a pointer to. TWO
    batteries (test_actor.py's spawn and reset, test_sound.py's stop chain)."""
    return opcode(0x4268 | base) + word(displacement)


def clr_b_d16(base, displacement):
    """...and the BYTE form. THREE batteries (test_actor.py, test_map.py, test_sound.py), which
    spelt it identically under one name and two argument names. test_hud.py is a fourth HALF-user:
    it carries whole assembled instructions as byte literals (`CLR_B_D16_A0`, `CLR_B_D16_A6`) inside
    larger composites rather than calling an encoder, so converting it is a change to that battery's
    style and not to this one's coverage."""
    return opcode(0x4228 | base) + word(displacement)


def clr_b_abs_l(addr):
    return opcode(0x4239) + longword(addr)


def clr_w_abs_l(addr):
    return opcode(0x4279) + longword(addr)


def clr_w_abs_w(addr):
    """...and the SHORT form, which is how the game clears a state word held below $8000 — the
    $a30/$a32/$a34 band and WB_SCROLL_FOLLOW_FROZEN. TWO batteries (test_stage.py's per-stage reset,
    test_scene.py's exit tail)."""
    return opcode(0x4278) + word(addr)


def st_abs_l(addr):
    """`st <abs>.l` — Scc with the always-true condition, which is how a flag byte is RAISED."""
    return opcode(0x50f9) + longword(addr)


def addq_w_abs_l(amount, addr):
    """`addq.w #n,<abs>.l` — how a free-running global counter is stepped. TWO batteries
    (test_scroll.py, test_rng.py's three PRNG counters)."""
    return opcode(0x5079 | ((amount & 7) << 9)) + longword(addr)


def subq_w_abs_l(amount, addr):
    """...and its twin, which lives beside it so the two cannot be got the wrong way round."""
    return opcode(0x5179 | ((amount & 7) << 9)) + longword(addr)


def addq_b_d16(amount, base, displacement):
    """`addq.b #n,d16(An)` — how a pass bumps a byte field of the actor record in place."""
    return opcode(0x5028 | ((amount & 7) << 9) | base) + word(displacement)


# A 68000 branch counts its displacement from the EXTENSION WORD, which sits two bytes after the
# opcode the branch is written as — so a displacement is always the bytes the branch spans plus that
# 2. The same 2 is what a `d16(pc)` OPERAND counts from, which is how test_sound.py's PC-relative
# module names every one of its own fields — one constant, because the two are the same rule.
# Spelling it once is what lets a pin's displacements come out of the geometry of the pieces they
# jump over instead of being transcribed. Each battery still keeps its own branch OPCODES (they
# spell them differently — byte constants in test_hud.py, built from an integer in test_scroll.py);
# `bsr.w` and `dbf` have only the one encoding each, so those are assembled whole here.
BRANCH_EXTENSION = 2
DBF_DN = 0x51c8


def forward_branch(spanned_bytes):
    """The displacement word of a `bcc.w`/`bra.w` that skips forward over ``spanned_bytes``."""
    return word(spanned_bytes + BRANCH_EXTENSION)


def backward_branch(body_bytes):
    """The displacement word of a `dbf`/`bra.w` that jumps BACK over the ``body_bytes`` it tails."""
    return word(-(body_bytes + BRANCH_EXTENSION))


def branch_over(condition, spanned_bytes):
    """`bcc.w`/`bra.w` past ``spanned_bytes``, for a jump whose target is known by LENGTH rather
    than by the pieces — a loop's own closing branch, or a `beq` over one `bsr`."""
    return opcode(condition) + forward_branch(spanned_bytes)


def branch(condition, *over):
    """`bcc.w`/`bra.w` past exactly ``over`` — the pieces themselves give the displacement."""
    return branch_over(condition, sum(len(piece) for piece in over))


def dbf_over(reg, body_bytes):
    """`dbf Dn,<back over ``body_bytes``>`, for a loop whose body is known by LENGTH."""
    return opcode(DBF_DN | reg) + backward_branch(body_bytes)


def dbf(reg, *body):
    """`dbf Dn,<start of body>`: the displacement runs back over ``body`` and the opcode word."""
    return dbf_over(reg, sum(len(piece) for piece in body))


def bsr_w(here, target):
    """`bsr.w target` as assembled AT ``here`` — a call's displacement depends on where it sits, so
    a pin aimed at the wrong callee (or built at the wrong offset) fails on the bytes."""
    return BSR_W + word(target - (here + BRANCH_EXTENSION))


def branch_w_to(condition, here, target):
    """`bcc.w`/`bra.w` aimed at an ABSOLUTE ``target``, as assembled AT ``here``.

    `branch_over` above is for a jump whose target is known by LENGTH; this is for one whose target
    is an address the battery already names — test_map.py's $1170 exits, which jump into another
    routine's tail, and every transfer test_scene.py pins out of the scene driver into a tail it
    declines to follow. Both spelt it identically under two names (`branch_w_to`, `branch_to`), so a
    displacement transcribed one instruction out fails on the bytes in either.
    """
    return opcode(condition) + word(target - (here + BRANCH_EXTENSION))


def assemble(base, pieces):
    """Concatenate ``pieces``; a callable piece is handed the address it starts at.

    Every pin whose operands are POSITION-DEPENDENT needs this — a `bsr.w` displacement, a
    `d16(pc)` operand — because such an operand cannot be built until the running address is known.
    test_hud.py's second tier spelt it first and test_sound.py's whole entry pin is one call to it,
    which is what moved it here."""
    body = b""
    for piece in pieces:
        body += piece(base + len(body)) if callable(piece) else piece
    return body


def assert_entry_is(name, expected):
    """Pin the bytes at ``name``'s entry against the instruction(s) the battery believes are there.

    This is what makes a wrong constant fail where it is wrong: a battery builds ``expected`` out of
    the encodings above and its own geometry constants, so one assert covers the entry point from
    ../names.txt, the global from include/wonderboy.h, the value, and the operand size all at once.
    """
    entry = entry_of(name)
    actual = bytes(harness.BASE_IMAGE[entry:entry + len(expected)])
    assert actual == expected, (
        f"{name} @ {entry:#x} is {actual.hex()}, not the {expected.hex()} this battery reconstructs")


def assert_batch_is_complete(entry_bytes, recorded):
    """Guard a battery's own scope: the entry-pin table must still hold the routines it was written
    for. ``recorded`` is a number the battery states rather than derives, so a routine dropped from a
    table shrinks the battery loudly instead of silently."""
    assert len(entry_bytes) == recorded, (
        f"{len(entry_bytes)} routines are reconstructed here, not the recorded {recorded} — a table "
        f"lost an entry, or gained one nothing else knows about")


# --- seeding an image a case can tell apart afterwards --------------------------------------------
# Two arbitrary odd multipliers, so that neighbouring addresses and neighbouring salts diverge in
# every bit rather than in the low ones. Nothing depends on their values, only on the mixing.
ADDRESS_MULTIPLIER = 0x9d
SALT_MULTIPLIER = 0x4f1b


def keyed_byte(addr, salt):
    """A byte derived from the ADDRESS, not from a row index.

    Batch 4's restore walk learned this the hard way: two widened bands that overlap let an
    index-keyed filler silently rewrite the earlier one, and the case then passes on bytes it did
    not mean to seed. Keyed on the address, an over-run lands on a byte that is wrong for where it
    was written.
    """
    mixed = (addr * ADDRESS_MULTIPLIER) ^ (addr >> 5) ^ (salt * SALT_MULTIPLIER)
    return (mixed ^ (mixed >> 8)) & 0xff


def keyed_block(base, length, salt):
    """One seeded band of ``keyed_byte``, built per call rather than cached: every case salts from
    its own NAME, so a cache would mostly retain bands nothing asks for again (measured on the
    scroll battery: it served under a third of the calls, all of them 8-bit salt collisions between
    unrelated cases, for 3% of the battery's time)."""
    return bytes(keyed_byte(base + offset, salt) for offset in range(length))


def overlay(*layers):
    """Poke dicts merged BYTE by byte, later layers winning, and re-banded into {start: bytes}.

    A poke dict is {address: bytes} and `dict.update` replaces a WHOLE entry — so a two-byte poke at
    the same address as an eleven-byte seed silently shortens the seed to two bytes and the other
    nine revert to whatever the .PRG ships there, with both cores reading the same wrong thing and
    every case staying green. THE HAZARD HAS FIRED TWICE: test_scene.py's `_poke` carries a comment
    about a band it lost to exactly this (the collision map "read as zeros for a batch"), and
    test_sound.py's tick tier had it twice before its review pass. It lives here so the third battery
    to build a layered seed does not have to find it a third time.

    ../STATUS.md registers the batteries that still merge by key (test_actor.py's `_defeat_pokes` and
    `_state_pokes`, test_map.py's `map_pokes`, and test_scene.py's own divergent refusal mechanism)
    as a queued consolidation rather than converting them here.
    """
    flat = {}
    for layer in layers:
        for addr, value in layer.items():
            for offset, byte in enumerate(value):
                flat[addr + offset] = byte
    return {start: bytes(flat[start + index] for index in range(length))
            for start, length in merge_bands(flat)}


def seeded_bytes(pokes):
    """Every ADDRESS a poke dict covers — the set `assert_bands_are_seeded` asks its question of."""
    return {addr + index for addr, value in pokes.items() for index in range(len(value))}


def assert_bands_are_seeded(pokes, bands, what):
    """Require ``pokes`` to cover every byte of each (base, length) in ``bands``.

    The other half of `overlay`: a battery whose routines read a MUTABLE image band has to state
    which bands those are, or a seeding bug leaves them on the shipped bytes and says nothing. The
    covered set is built ONCE rather than per band — it is the whole poke dict either way.
    """
    covered = seeded_bytes(pokes)
    for base, length in bands:
        missing = sorted(a for a in range(base, base + length) if a not in covered)
        assert not missing, (
            f"{what}: {len(missing)} byte(s) of the band at {base:#x} are NOT seeded, e.g. "
            f"{missing[0]:#x} — that byte runs on the .PRG's own residue")


def case_salt(case):
    """A salt derived from the case's NAME, and derived reproducibly.

    Python's `hash()` of a string is randomised per process unless PYTHONHASHSEED is pinned, which
    nothing here pins — seeding from it would give every run a different image, so a failure could
    not be replayed from its case id and a mutation sweep's red count could move between sweeps
    without the code changing. `crc32` is the same number in every process.
    """
    return zlib.crc32(case.encode()) & 0xff


# --- reading the image the same way the 68000 does ------------------------------------------------
# A battery that states its write set EXACTLY models the routine's own arithmetic in Python, and
# every such model reads words out of the image and sign-extends them. Three batteries spelt these
# (test_scroll.py, test_actor.py, test_map.py), which is a third place the sign extension could have
# been got wrong.
WORD_BYTES = 2

# ...and the longword, which every battery that reads a pointer or a `movem` slot out of the image
# needs. test_hud.py and test_sound.py take it from here; test_actor.py, test_blit.py, test_map.py
# and test_scroll.py still spell a `LONGWORD_LEN = 4` of their own and are the next conversion —
# stated rather than left silent, the way an encoding parked at two users says so in its docstring.
LONGWORD_BYTES = 4


def u16(image, addr):
    """The word at ``addr``, as the big-endian number a `move.w` reads there."""
    return int.from_bytes(bytes(image[addr:addr + WORD_BYTES]), "big")


def s16(value):
    """``value``'s low word as the SIGNED number a word operand spells."""
    value &= WORD_MASK
    return value - (WORD_MASK + 1) if value & 0x8000 else value


def s8(value):
    """``s16`` one size down: ``value``'s low BYTE as the signed number `ext.w Dn` makes of it.

    TWO batteries (test_blit.py's sprite descriptor, whose height and width-code fields are signed
    bytes, and test_sound.py's SFX id and volume index) — and the reconstruction spells it once too,
    as `sign_ext8` in tools/recreate_kit/include/machine.h.
    """
    value &= 0xff
    return value - 0x100 if value & 0x80 else value


# --- the register arithmetic a model restates -----------------------------------------------------
# The reconstruction does these through tools/recreate_kit/include/machine.h; a model that spelt one
# of them differently would agree with the reconstruction only by luck, so they live here under
# machine.h's own names. Three batteries rotate a longword (test_blit.py's sub-word shift,
# test_scroll.py's tile loop, test_hud.py's digit register) and two write a word into one
# (test_blit.py's row counter, test_map.py's probe fields).
LONG_BITS = 32
HIGH_WORD_MASK = LONGWORD_MASK - WORD_MASK   # 0xffff0000: the half a `.w` write leaves alone


def rotate_left32(value, count):
    """68k `rol.l Dm,Dn` — a 32-bit ROTATE: the bits that leave the top come back in at the bottom.

    The `& 31` is machine.h's and the 68000's: it rotates by the count mod 64, and a 32-bit rotate
    is cyclic mod 32, so the mask is exact rather than a clamp — and it makes a count of 0 the
    machine's own no-op instead of Python's `value >> 32`, which is 0 and not the identity.
    """
    count &= LONG_BITS - 1
    if count == 0:
        return value & LONGWORD_MASK
    return ((value << count) | (value >> (LONG_BITS - count))) & LONGWORD_MASK


def rotate_right32(value, count):
    """68k `ror.l Dm,Dn`, DERIVED from the left one rather than written twice: a 32-bit rotate is
    cyclic, so rotating right by n is rotating left by 32 - n."""
    return rotate_left32(value, LONG_BITS - (count & (LONG_BITS - 1)))


def set_low_word(value, low):
    """A `.w` write into a longword register: the low word is replaced and the caller's HIGH half
    survives it. This is how a 68000 routine returns "a word" in a register the differential
    compares as a longword."""
    return (value & HIGH_WORD_MASK) | (low & WORD_MASK)


# --- reading a value back out of the oracle's write set -------------------------------------------

def read_bytes(info, addr, length, what=""):
    """The bytes the original left at ``addr``, taken from the oracle's write set.

    This is what lets a case say WHICH value it expects rather than only that both sides agree. A
    byte the original never wrote is a failure and not a fallback to the image: the case would
    otherwise pass on whatever was already there.
    """
    writes = info["writes"]
    missing = [addr + i for i in range(length) if addr + i not in writes]
    assert not missing, (
        f"{what}: the original did not write {[hex(a) for a in missing]}; it wrote "
        f"{[hex(a) for a in sorted(writes)][:8]}...")
    return bytes(writes[addr + i] for i in range(length))


def read_int(info, addr, length, what=""):
    """``read_bytes`` as the big-endian number those bytes spell."""
    return int.from_bytes(read_bytes(info, addr, length, what), "big")


def assert_written_is(info, model, what, extra=frozenset()):
    """The run's write set is EXACTLY ``model``'s addresses, and every byte holds ``model``'s value.

    ``model`` is {address: bytes}, the shape a composed battery's model returns. ``extra`` is a set
    of addresses the case has declared it CHECKS FOR ITSELF — the boss arm's eighteen actor records
    are the one user — and the rule is that the two are DISJOINT: an address is modelled here or
    checked there, never both. That is refused by name rather than resolved, because either
    resolution is wrong. Exempting an address from the actual side alone (which this did) leaves the
    model still value-checking a byte the case said it owned, and makes an overlap fail the SET
    comparison with a message about counts that names neither address; exempting it from both sides
    silently drops a modelled byte nothing then checks.

    The failure names the FIRST byte that differs and the band it belongs to, because a 180 KB model
    whose report is "they differ" is not usable.

    Hoisted out of test_stage.py's `_run_load_window` when test_scene.py's composed runs became its
    second and third caller: two copies of a comparison this size could drift on what counts as a
    match while both batteries stayed green.
    """
    written = seeded_bytes(model)
    overlap = sorted(written & set(extra))
    assert not overlap, (
        f"{what}: {len(overlap)} address(es) are both modelled and declared self-checked, e.g. "
        f"{overlap[0]:#x} — an address belongs to one side or the other")
    actual = program_writes(info)
    assert set(actual) - set(extra) == written, (
        f"{what}: the original wrote {len(actual)} bytes against the model's {len(written)} "
        f"(+{len(extra)} the case checks itself)")
    for addr, expected in sorted(model.items()):
        got = read_bytes(info, addr, len(expected), what)
        if got != expected:
            at = next(i for i in range(len(expected)) if got[i] != expected[i])
            raise AssertionError(
                f"{what}: {addr + at:#x} is {got[at]:#04x}, not the {expected[at]:#04x} the model "
                f"gives (band at {addr:#x}, {len(expected)} bytes)")


def assert_rows(info, rows, expected, what, skip=()):
    """Compare a blit's rows against the bytes the case says should have moved.

    ``rows`` is the [(address, length)] the run was allowed to write — the same list the caller hands
    ``run()`` — and ``expected`` the bytes for each of them. The rectangular blits all compare their
    result this way, so the row index and the differing bytes are named in one place.

    ``skip`` is a set of addresses to leave out, for the case where a SECOND draw lands inside the
    first one's rectangle and those bytes belong to that draw's own assert (test_hud.py's record
    display stamps two digits into the bitmap it just blitted). A ``skip`` that swallowed the whole
    rectangle would turn this into a no-op, so the bytes actually compared are counted and required
    to be a majority of them — the row/length check above does not cover that on its own.
    """
    assert len(expected) == len(rows), (
        f"{what}: {len(expected)} expected rows against {len(rows)} written ones — a case whose two "
        f"geometries disagree would leave the surplus rows unchecked")
    compared = 0
    for row, (addr, length) in enumerate(rows):
        actual = read_bytes(info, addr, length, what)
        # Per ROW as well as per row COUNT: `expected` is normally sliced out of the loaded image,
        # and a slice that ran past the end comes back short — which would be an IndexError inside
        # this loop rather than a failure naming the case.
        assert len(expected[row]) == length, (
            f"{what}: expected row {row} is {len(expected[row])} bytes against the {length} written "
            f"— the case's source geometry and its destination geometry disagree")
        for index in range(length):
            if addr + index in skip:
                continue
            compared += 1
            assert actual[index] == expected[row][index], (
                f"{what}: row {row} byte {index} at {addr + index:#x} is {actual[index]:#04x}, not "
                f"{expected[row][index]:#04x} (row is {actual.hex()}, not {expected[row].hex()})")
    total = sum(length for _addr, length in rows)
    assert compared * 2 > total, (
        f"{what}: only {compared} of {total} bytes were compared — the skip set has swallowed the "
        f"blit, so this assert is holding almost nothing")


# --- the two off-image surfaces the DIRECT PSG path leaves ----------------------------------------

def assert_psg_surfaces(info, events, values, known, what):
    """The ordered access ledger and the register file a run leaves, against what a case states.

    HERE BECAUSE NOTHING IN THE IMAGE CAN SHOW EITHER. A run that drove the wrong register, or none
    at all, writes exactly the same memory (tools/recreate_kit/TRAP_MODEL.md, "Phase 6"), so a second
    spelling of this pair is a battery that can go on asserting a strictly weaker surface than the
    first while both stay green. test_sound.py had exactly two — the stop chain's, whose expectation
    is computed from the seed, and the tick's, which RECORDS its ledger as the model runs — which is
    what moved it here.

    ``events`` is the expected ``[(kind, register, value)]``, ``values`` the whole register file and
    ``known`` its bit-per-register mask. QUEUED, not done: test_actor.py asserts one of the two
    piecemeal (`psg_events == []` for a path that must not touch the chip) and is the third caller
    this wants; converting it is registered in ../STATUS.md rather than folded in here.
    """
    assert info["regs"]["psg_events"] == events, (
        f"{what}: the chip saw {info['regs']['psg_events']}, not {events} "
        f"(each entry is (kind, register, value); a read-back is kind {harness.OS_PSG_EVENT_READ})")
    assert (info["regs"]["psg_file"], info["regs"]["psg_known"]) == (bytes(values), known), (
        f"{what}: the register file ended {info['regs']['psg_file'].hex()} "
        f"(known {info['regs']['psg_known']:#06x}), not {bytes(values).hex()} (known {known:#06x})")
