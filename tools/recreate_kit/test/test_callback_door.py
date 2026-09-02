"""Pin the CALLBACK DOOR — how an asm twin run under Musashi calls a HOST C core (TRAP_MODEL.md).

The door exists because a twin transcribes the original's instructions, so it calls what the
original calls, and off target some of those callees are host C: the verified cores in a project's
candidate `.so`, two of whose seams (`sched_wait8`, `hw_bset8`) are modelled host-side as well. On
the machine the twin links against the real cores and the stub jumps straight to one. So the door is
the off-target stand-in for a link — and being off-target-only is exactly what makes it dangerous:
anything it does that the target build does not do is a difference no surface here can see.

The twins are assembled FROM THIS FILE into a temp directory rather than borrowed from a project's
`src/asm/`, so the kit's own suite pins the kit's own machinery and names no game. The host "cores"
are `door_probe.c` next door, compiled into a throwaway `.so` — a stand-in for the candidate library
a real project passes as `harness._lib`.

WHAT IT PINS, and each of these is a thing that would otherwise be silent:

  * the whole path: a twin's `bsr` reaches the band, the host function runs, its answer comes back in
    D0 and its writes are in the image;
  * an UNREGISTERED slot REFUSES rather than answering 0 — a twin calling a door nobody declared
    would otherwise pass on an answer no core gave;
  * the marshalling, by MUTATION: shift the substituted image pointer, drop an argument, or fail to
    pop the return frame, and the case reddens. Each of the three is a defect the door could have
    and the image comparison could not see;
  * the door is a PLAIN C CALL: the emulated CCR and every register but D0 come back exactly as the
    twin left them. This is the check that would catch flag marshalling being put back into the
    door, where it would run off target only;
  * the band's placement between the twin's stack and the image, which `AsmTwins` asserts;
  * a run with NO door behaves exactly as it did before there was one.
"""
from pathlib import Path

import pytest

# A bench budget small enough that a twin which never leaves the door reddens instead of
# hanging, and small enough to be obviously below any probe twin's legitimate work.
# Named because it is spelt at two call sites and neither is self-explanatory as a bare 200.
SHRUNK_INSN_CAP = 200

import kit_smoke_project
import probe_build

# `emu` derives its constants from a bound project at import, and this directory binds none of its
# own — so the miniature one the kit's other plumbing suites use is what makes `import emu` possible
# here. Its candidate `.so` is not used: the door's callees are `door_probe.c`, built below.
kit_smoke_project.bind()

import emu           # noqa: E402  (importable only once a project is bound)

from recreate_kit import asm_twin        # noqa: E402
from recreate_kit.asm_twin import AsmTwins, DoorCallback   # noqa: E402

KIT = Path(__file__).resolve().parents[1]
HOST_SRC = Path(__file__).with_name("door_probe.c")

# The door slots the probe twins' stubs jump to. 0 and 2 are declared by the table below; 9 is
# deliberately not, and is what the refusal case reaches.
SUM_SLOT = 0
MARK_SLOT = 2
NO_IMAGE_SLOT = 3
VOID_SLOT = 4
UNDECLARED_SLOT = 9

# door_probe.c's constants, mirrored — the C file is the source and this asserts against it.
MARK_AT = 0x40
MARK = 0xA5
MARK_RESULT = 0x0BADF00D

# Where probe_state records the emulated machine's state either side of its door call. Interpolated
# into the assembly below, so the two spellings cannot drift.
SP_ENTRY_AT = 0x00
SP_EXIT_AT = 0x04
A1_AT_EXIT = 0x08
RESULT_AT = 0x0C
SR_BEFORE_AT = 0x10          # word
SR_AFTER_AT = 0x12           # word
A0_AT_EXIT = 0x14
D1_AT_EXIT = 0x18

A1_WITNESS = 0x0123ABCD      # a caller-saved register the door is EXPECTED to destroy
CONDITION_CODE_BITS = 0x1F   # X N Z V C — cleared before the door, and required set after

# What door_probe_no_image_host makes of its two arguments, and what probe_no_image pushes.
NO_IMAGE_A, NO_IMAGE_B = 0x00BEEF00, 0x0000CAFE
NO_IMAGE_EXPECTED = NO_IMAGE_A + 2 * NO_IMAGE_B

# What probe_sum passes and what door_probe_sum_host makes of it: a + 2b + 4c, so no two arguments
# carry the same weight and a dropped or reordered one changes the answer.
SUM_A, SUM_B, SUM_C = 0x11, 0x220, 0x3300
SUM_EXPECTED = SUM_A + 2 * SUM_B + 4 * SUM_C

# probe_sum's own instructions: four argument reads, four pushes, the `bsr`, the `lea` that drops the
# frame and the `rts` — eleven — plus the stub's `jmp`, which really executes and is really charged.
PROBE_SUM_INSNS = 12
# ...and what osh_run_bench counts on top: Musashi's first m68k_execute() after a reset spends the
# reset's cycles and executes NO instruction, so every bench run's tally is one high (shim.c says so
# where it counts, and every pinned perf number in this workspace includes it).
RESET_OBSERVATION = 1

_ASM = f"""
| Probe twins for the CALLBACK DOOR (test_callback_door.py). Assembled from the test rather than
| kept in a project's src/asm/, so the kit's suite pins the kit's machinery and names no game.
|
| Each door callee gets a one-instruction stub, exactly as a real twin's does: off target it jumps
| into the band, on target it would jump to the C core itself. The bodies below always `bsr.w` the
| stub, so they would be byte-identical in a target build.
|
| Only d0/d1/a0/a1 are used: d2-d7 and a2-a6 are callee-saved, and AsmTwins.call seeds them and
| requires them back, so a probe touching one would fail for a reason that is not its own.
    .text

| long probe_sum(uint8_t *image, long a, long b, long c) — hand all four to the host core.
    .globl probe_sum
probe_sum:
    movea.l 4(%sp),%a0                | the image base
    move.l  8(%sp),%d0                | a
    move.l  12(%sp),%d1               | b
    movea.l 16(%sp),%a1               | c, parked in the other scratch address register
    move.l  %a1,-(%sp)
    move.l  %d1,-(%sp)
    move.l  %d0,-(%sp)
    move.l  %a0,-(%sp)                | ...argument 0 is the image base, as every core's is
    bsr.w   door_probe_sum
    lea     16(%sp),%sp
    rts

| long probe_state(uint8_t *image) — call the door and record what the machine looked like either
| side of it, so the test can require that nothing but D0 moved.
    .globl probe_state
probe_state:
    move.l  %a2,-(%sp)                | a2 is callee-saved: keep the caller's and use it as our base,
    movea.l 8(%sp),%a2                | because a0/a1 do not survive a call and must not be relied on
    move.l  %a7,{SP_ENTRY_AT}(%a2)
    movea.l #{A1_WITNESS:#x},%a1      | a caller-saved witness: the door is expected to destroy it
    move.l  %a2,-(%sp)                | argument 0: the image base
    move.w  #0,%ccr                   | every condition code CLEAR — the door must leave them set
    move.w  %sr,%d0                   | move-from-SR leaves the CCR alone, so this reads the pattern
    move.w  %d0,{SR_BEFORE_AT}(%a2)   | ...but the store does disturb it,
    move.w  #0,%ccr                   | ...so this is the CCR the door is actually handed
    bsr.w   door_probe_mark
    move.w  %sr,-(%sp)                | park the flags before any store of ours disturbs them
    move.l  %d1,{D1_AT_EXIT}(%a2)     | ...which is also why d1 cannot be the place to park them
    move.l  %d0,{RESULT_AT}(%a2)
    move.l  %a0,{A0_AT_EXIT}(%a2)
    move.l  %a1,{A1_AT_EXIT}(%a2)
    move.w  (%sp)+,{SR_AFTER_AT}(%a2)
    lea     4(%sp),%sp
    move.l  %a7,{SP_EXIT_AT}(%a2)
    movea.l {SP_ENTRY_AT}(%a2),%a7    | a no-op after a correct door; after a mutated one it is what
    movea.l (%sp)+,%a2                | keeps the damage RECORDED above rather than fatal below
    rts

| long probe_undeclared(uint8_t *image) — a stub whose slot no callback table declares.
    .globl probe_undeclared
probe_undeclared:
    movea.l 4(%sp),%a0
    move.l  %a0,-(%sp)
    bsr.w   door_probe_undeclared
    lea     4(%sp),%sp
    rts

| long probe_door_loop(uint8_t *image) — call the door forever. Nothing in the twin ends this run;
| only the RUN's instruction budget can, which is the property the case about it is for.
    .globl probe_door_loop
probe_door_loop:
.Lprobe_door_loop:
    movea.l 4(%sp),%a0                | reloaded every pass: a0 does not survive a call
    move.l  %a0,-(%sp)
    bsr.w   door_probe_mark
    lea     4(%sp),%sp
    bra.s   .Lprobe_door_loop

| long probe_door_returns_into_the_door(uint8_t *image) — a broken stub whose "return address" is
| itself a door address, so servicing one callback lands straight on the next having executed
| NOTHING. A budget alone never ends that: no segment spends an instruction.
    .globl probe_door_returns_into_the_door
probe_door_returns_into_the_door:
    movea.l 4(%sp),%a0
    move.l  %a0,-(%sp)                | argument 0
    pea     (RECREATE_DOOR_BASE + {MARK_SLOT} * RECREATE_DOOR_STRIDE).l
    jmp     (RECREATE_DOOR_BASE + {MARK_SLOT} * RECREATE_DOOR_STRIDE).l

| long probe_no_image(uint8_t *image, long a, long b) — reach a core that takes NO image, the shape
| of a hardware seam. Nothing is substituted; both words arrive as the twin pushed them.
    .globl probe_no_image
probe_no_image:
    move.l  12(%sp),-(%sp)            | b
    move.l  12(%sp),-(%sp)            | a  (the push above moved the frame by 4)
    bsr.w   door_probe_no_image
    lea     8(%sp),%sp
    rts

| long probe_void(uint8_t *image) — reach a core declared `void`, whose D0 is undefined on target.
    .globl probe_void
probe_void:
    movea.l 4(%sp),%a0
    move.l  %a0,-(%sp)
    bsr.w   door_probe_void
    lea     4(%sp),%sp
    rts

| long probe_wrong_base(uint8_t *image) — push something that is NOT the image base as argument 0.
    .globl probe_wrong_base
probe_wrong_base:
    movea.l 4(%sp),%a0
    lea     4(%a0),%a0                | one longword past the base: the shape of a twin that has
    move.l  %a0,-(%sp)                | computed its base wrong
    bsr.w   door_probe_mark
    lea     4(%sp),%sp
    rts

| long probe_clobbers_d5(uint8_t *image) — return without restoring a callee-saved register, which
| is the `movem` defect nothing but the seeded check can see. No door: the defect is not the door's.
    .globl probe_clobbers_d5
probe_clobbers_d5:
    moveq   #0,%d5
    rts

| long probe_pure(uint8_t *image, long a, long b) — no door at all, for the no-door contract.
    .globl probe_pure
probe_pure:
    move.l  8(%sp),%d0
    add.l   12(%sp),%d0
    rts

| ---- the stubs: the only place a door address is ever spelt ----
| Both arms are here, chosen by the marker kit.mk defines for the OFF-TARGET assembly alone, which is
| how a real twin's stubs are written — and the band comes from kit.mk's `-D`s rather than from a
| copy of the number, so a `.S` cannot keep jumping to an address the band has left.
#ifdef RECREATE_HOST_DIFFERENTIAL
# define DOOR_STUB(slot) jmp (RECREATE_DOOR_BASE + (slot) * RECREATE_DOOR_STRIDE).l
#else
| ...spelt `(label).l` so the target arm is the same 6-byte absolute-long `jmp` a real twin's is:
| its callee is an EXTERNAL symbol, and gas would shorten a jump to this file's own label to a
| 4-byte PC-relative one, changing every `bsr` displacement above it for a reason that is an
| artifact of the probe rather than a fact about either build.
# define DOOR_STUB(slot) jmp (probe_stand_in_core).l
#endif

door_probe_sum:
    DOOR_STUB({SUM_SLOT})
door_probe_mark:
    DOOR_STUB({MARK_SLOT})
door_probe_no_image:
    DOOR_STUB({NO_IMAGE_SLOT})
door_probe_void:
    DOOR_STUB({VOID_SLOT})
door_probe_undeclared:
    DOOR_STUB({UNDECLARED_SLOT})

| What the target build's stubs reach instead of the band: a probe has no real C cores to link.
probe_stand_in_core:
    rts
"""


@pytest.fixture(scope="module")
def asm_dir(tmp_path_factory):
    """Assemble the probe twins exactly as kit.mk assembles a project's — probe_build owns the how,
    so a flag the kit adds for the twins (the door's own marker, for one) reaches these too."""
    return probe_build.assemble_twins(_ASM, tmp_path_factory.mktemp("door_twins"))


@pytest.fixture(scope="module")
def target_asm_dir(tmp_path_factory):
    """The same source assembled as a project's TARGET build assembles it: no off-target marker, so
    every stub takes its `jmp <core>` arm."""
    return probe_build.assemble_twins(_ASM, tmp_path_factory.mktemp("door_twins_target"),
                                      flags=probe_build.asm_flags(host_differential=False))


@pytest.fixture(scope="module")
def host_lib(tmp_path_factory):
    """The host "cores" the door calls — a stand-in for a project's candidate `.so`."""
    return probe_build.build_host_lib(HOST_SRC, tmp_path_factory.mktemp("door_hosts"),
                                      "libdoorprobe.so")


@pytest.fixture
def table():
    """The project-supplied callback table: slot -> what lives behind it. Declarative, and the kit
    half never names one of these."""
    return {SUM_SLOT: DoorCallback("door_probe_sum_host", 4),
            MARK_SLOT: DoorCallback("door_probe_mark_host", 1),
            NO_IMAGE_SLOT: DoorCallback("door_probe_no_image_host", 2, takes_image=False),
            VOID_SLOT: DoorCallback("door_probe_void_host", 1, returns=False)}


@pytest.fixture
def twins(asm_dir, host_lib, table):
    return AsmTwins(asm_dir, kit_smoke_project.IMAGE_SIZE, callbacks=table, lib=host_lib)


@pytest.fixture
def image():
    return bytes(kit_smoke_project.IMAGE_SIZE)


def _make_assignment(makefile, name):
    """The right-hand side of `name := ...`, continuation lines joined — enough Makefile parsing to
    ask what flags the twins are really assembled with, and no more."""
    lines = makefile.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{name} :="):
            value = line.split(":=", 1)[1]
            while value.rstrip().endswith("\\"):
                i += 1
                value = value.rstrip().rstrip("\\") + " " + lines[i]
            return value.strip()
    raise AssertionError(f"kit.mk has no `{name} :=` — this pin is looking at the wrong name")


def _blob(asm_dir):
    return (Path(asm_dir) / "twins.bin").read_bytes()


def _bodies_span(asm_dir):
    """[first twin, first stub) in the assembled blob — every twin BODY and no stub.

    The stubs are last in the source, so one span covers all four bodies; taking it from the symbol
    table rather than by counting bytes means a probe gaining a twin does not silently narrow it.
    """
    symbols = asm_twin.elf_symbols(Path(asm_dir) / "twins.elf")
    return symbols["probe_sum"][0], symbols["door_probe_sum"][0]


def _u32(image, at):
    return int.from_bytes(image[at:at + 4], "big")


def _u16(image, at):
    return int.from_bytes(image[at:at + 2], "big")


def test_a_twin_calls_a_host_core_through_the_door(twins, image):
    """The whole path, end to end: the twin's `bsr` reaches the band, the host C function runs over
    the real image, its answer comes back in D0 and its write is in the image the call returns."""
    out = twins.call(image, "probe_sum", SUM_A, SUM_B, SUM_C)
    assert out.d0 == SUM_EXPECTED, "the host core's answer did not reach D0"
    assert out.image[MARK_AT] == MARK, (
        "the host core's write is not in the image — argument 0 was not a pointer INTO it")


def test_the_door_charges_the_emulated_machine_nothing(twins, image):
    """The twin's `bsr` and the stub's `jmp` really execute and are really charged; the host C body
    does not exist on the target this measures, so it must cost nothing.

    That matters beyond tidiness: an off-target cost pin over a twin that calls cores measures the
    twin's OWN instructions, and the callee's cost is measured on target, against the original's own
    call to the same routine. A door that charged for the service would corrupt both halves.
    """
    out = twins.call(image, "probe_sum", SUM_A, SUM_B, SUM_C)
    assert out.ninsns == PROBE_SUM_INSNS + RESET_OBSERVATION


def test_an_undeclared_slot_refuses_instead_of_answering(twins, image):
    """A twin calling a door nobody registered has no host core behind it. Answering 0 would be a
    fabricated result the whole differential would then agree with — the `$ffff820a` shape."""
    with pytest.raises(KeyError, match="no callback table entry declares"):
        twins.call(image, "probe_undeclared")


def test_the_refusal_is_not_a_quiet_zero(monkeypatch, twins, image):
    """...and this is what says the refusal is load-bearing rather than decorative: with it stubbed
    out to the fabricated 0, the same twin runs to completion and reports a clean answer."""
    def fabricate(self, mem, buf, door_pc):
        emu.bench_door_return(0, *asm_twin._door_rts(mem, emu.bench_door_sp()))

    monkeypatch.setattr(AsmTwins, "_service_door", fabricate)
    out = twins.call(image, "probe_undeclared")
    assert out.d0 == 0, (
        "the fabricated answer did not reach D0, so this case is not measuring the refusal")


def test_the_door_leaves_the_frame_and_the_result_as_a_call_would(twins, image):
    """What a C call does NOT disturb: the stack it was called on, and the callee-saved file — which
    `AsmTwins.call` checks on every call, this one included. The answer arrives in D0."""
    out = twins.call(image, "probe_state")
    assert _u32(out.image, SP_EXIT_AT) == _u32(out.image, SP_ENTRY_AT), (
        "the door left the twin's stack pointer somewhere else")
    assert _u32(out.image, RESULT_AT) == MARK_RESULT and out.d0 == MARK_RESULT


def test_the_door_destroys_what_a_real_core_destroys(twins, image):
    """...and what it DOES disturb, which is the half that would otherwise be an off-target-only
    contract. On the machine this call site reaches the actual core, and the m68k SysV ABI lets it
    wreck D0, D1, A0, A1 and every condition-code bit. A door that politely preserved them would
    make a stub that forgot to save its scratch file — or that branched on a flag its callee
    happened to leave — pass here and fail on the STE, with nothing off target able to say so.

    So `probe_state` hands the door a CLEARED condition-code register and a witness in `%a1`, and
    requires both to come back wrecked.
    """
    out = twins.call(image, "probe_state")
    assert _u16(out.image, SR_BEFORE_AT) & CONDITION_CODE_BITS == 0, (
        "the twin did not hand the door the cleared flags this case is about")
    assert _u16(out.image, SR_AFTER_AT) & CONDITION_CODE_BITS == CONDITION_CODE_BITS, (
        "the door preserved the condition codes, which a real core does not")
    assert _u32(out.image, A1_AT_EXIT) != A1_WITNESS, (
        "the door preserved a caller-saved register, which a real core does not")
    assert _u32(out.image, D1_AT_EXIT) == emu.DOOR_SCRATCH_POISON + 1
    assert _u32(out.image, A0_AT_EXIT) == emu.DOOR_SCRATCH_POISON + 2
    assert _u32(out.image, A1_AT_EXIT) == emu.DOOR_SCRATCH_POISON + 3


def test_a_core_that_takes_no_image_gets_its_own_arguments(twins, image):
    """Not every callee takes the image: a hardware seam (`hw_bset8(addr, bit)`) or a device command
    (`ikbd_send_cmd(cmd)`) has none to be handed, and substituting a host pointer over its first
    argument would corrupt exactly the value it needs — the mirror of the mistake the substitution's
    own check exists to catch. Such a core declares `takes_image=False`, and every word arrives as
    the twin pushed it."""
    out = twins.call(image, "probe_no_image", NO_IMAGE_A, NO_IMAGE_B)
    assert out.d0 == NO_IMAGE_EXPECTED


def test_a_core_that_returns_nothing_leaves_d0_undefined(twins, image):
    """A `void` core's D0 on the machine is whatever it happened to leave, so the door poisons D0
    rather than reading the host's arbitrary return register: a value undefined on target must not
    be a definite number here, or a stub that branched on it would pass off target and flake on the
    machine. The host stand-in returns a value the case would recognise; it must not appear."""
    out = twins.call(image, "probe_void")
    assert out.d0 == emu.DOOR_SCRATCH_POISON
    assert out.image[MARK_AT] == MARK, "the void core did not run at all"


def _mutate_door_args(monkeypatch, transform):
    """Run `AsmTwins._door_args` and hand the result through `transform` — the one way the mutation
    cases below bend the marshalling, so each of them is its own one-line defect and nothing else."""
    original = AsmTwins._door_args
    monkeypatch.setattr(AsmTwins, "_door_args",
                        lambda self, mem, buf, sp, cb: transform(original(self, mem, buf, sp, cb)))


def test_a_shifted_image_pointer_reddens(monkeypatch, twins, image):
    """MUTATION: the door substitutes a host pointer for argument 0. Move it, and the host core's
    write lands somewhere else — which is what the mark assertion is for.

    It shifts rather than passing the raw emulated base, deliberately: the emulated base is not a
    host address, so passing it would segfault the worker, and a dead worker is not a red.
    """
    shift = 0x10
    _mutate_door_args(monkeypatch, lambda args: [args[0] + shift] + args[1:])
    out = twins.call(image, "probe_sum", SUM_A, SUM_B, SUM_C)
    assert out.image[MARK_AT] != MARK and out.image[MARK_AT + shift] == MARK


def test_a_skipped_argument_reddens(monkeypatch, twins, image):
    """MUTATION: read the callee's arguments one stack slot too high — the classic off-by-one-word —
    and `a` is lost, `b` and `c` slide down and the weighted sum is a different number."""
    _mutate_door_args(monkeypatch, lambda args: args[:1] + args[2:] + [0])
    out = twins.call(image, "probe_sum", SUM_A, SUM_B, SUM_C)
    assert out.d0 != SUM_EXPECTED


def test_a_return_frame_left_on_the_stack_reddens(monkeypatch, twins, image):
    """MUTATION: simulate the stub's `rts` without dropping the return address. The twin resumes at
    the right instruction with its stack one longword low, and `probe_state`'s own record of A7
    either side of the call is what says so.

    Recorded rather than expected-to-crash on purpose: a twin left on a shifted stack `rts`es to
    whatever word is under it, and where THAT lands is an accident of the layout — it can even walk
    back to the sentinel and report a clean run. The frame is a fact the twin can measure, so it is
    measured.
    """
    monkeypatch.setattr(asm_twin, "_door_rts",
                        lambda mem, sp: (int.from_bytes(mem[sp:sp + 4], "big"), sp))
    out = twins.call(image, "probe_state")
    assert _u32(out.image, SP_EXIT_AT) != _u32(out.image, SP_ENTRY_AT)


def test_a_base_that_is_not_the_image_base_is_refused(twins, image):
    """The door substitutes a host pointer for argument 0, and it checks what it is substituting OVER.
    A twin that computed the wrong base would otherwise have that mistake corrected for it — the
    callback would run over the right image and the case would pass, while on target the same twin
    hands the core a pointer four bytes off."""
    with pytest.raises(AssertionError, match="not the image base"):
        twins.call(image, "probe_wrong_base")


def test_a_twin_that_loses_a_callee_saved_register_is_caught(twins, image):
    """The `movem` defect the seeded file exists for, driven here rather than only on a project's
    twins: `probe_clobbers_d5` writes a callee-saved register and never restores it. Its image is
    perfect, it returns cleanly and it balances its stack — the register is the only trace."""
    with pytest.raises(AssertionError, match="returned with d5"):
        twins.call(image, "probe_clobbers_d5")


def test_a_twin_that_never_leaves_the_door_spends_the_runs_budget(monkeypatch, twins, image):
    """`bench_resume` takes a fresh cap per segment, so the door loop must spend the RUN's budget
    rather than the segment's. Without that, a twin that keeps re-entering the door never ends —
    `make test` HANGS instead of reddening, and a hung suite decides nothing.

    The budget is shrunk rather than waited out: what is being pinned is the arithmetic, and sixteen
    million instructions of it prove nothing the first two hundred do not.
    """
    monkeypatch.setattr(emu, "BENCH_MAX_INSNS", SHRUNK_INSN_CAP)
    with pytest.raises(RuntimeError, match="did not return to the sentinel"):
        twins.call(image, "probe_door_loop")


def test_a_callback_that_returns_into_the_door_is_refused(twins, image):
    """...and the shape a budget alone cannot end: every segment stops after ZERO instructions, so
    the budget never shrinks. That is a frame bug in the stub, and it is named as one."""
    with pytest.raises(AssertionError, match="straight back into the door band"):
        twins.call(image, "probe_door_returns_into_the_door")


def test_the_twin_bodies_are_byte_identical_in_both_builds(asm_dir, target_asm_dir):
    """The claim the whole stub arrangement rests on: a twin's BODY is the same bytes off target and
    on, because the only thing that changes is the one instruction inside the stub.

    Assembled here both ways — with the kit's off-target marker and without it — and compared over
    everything from the first twin to the first stub. Without this the marker names no surface: a
    `.S` whose door arm quietly changed a body instruction would ship a twin the differential
    verified and the target never ran.
    """
    off_target, on_target = _blob(asm_dir), _blob(target_asm_dir)
    spans = [_bodies_span(asm_dir), _bodies_span(target_asm_dir)]
    assert spans[0] == spans[1], "the bodies do not even start and end at the same addresses"
    lo, hi = spans[0]
    assert off_target[lo:hi] == on_target[lo:hi]


def test_kit_mk_assembles_the_twins_the_way_this_suite_does():
    """The flags live in Python (`probe_build.asm_flags`) and in make (`kit.mk`'s ASM_CFLAGS), and
    the make one is what a project's `make test` really runs. Every case above builds through the
    Python one, so a `-D` dropped from the Makefile would be invisible to all of them — including
    the off-target marker that selects a door stub's arm and the band the stub jumps to.
    """
    kit_mk = (KIT / "kit.mk").read_text()
    asm_cflags = _make_assignment(kit_mk, "ASM_CFLAGS")
    for flag in probe_build.asm_flags():
        if flag.startswith("-DRECREATE_DOOR_"):
            continue                          # delivered through $(ASM_DOOR_FLAGS), checked below
        assert flag in asm_cflags, f"kit.mk assembles the twins without {flag}"
    assert "$(ASM_DOOR_FLAGS)" in asm_cflags, (
        "kit.mk does not pass the door's band to the assembler, so a `.S` has no way to reach it "
        "but to spell the address itself — the drift asm_door_flags() exists to prevent")
    assert "asm_twin.asm_door_flags()" in _make_assignment(kit_mk, "ASM_DOOR_FLAGS"), (
        "kit.mk spells the band itself rather than asking asm_twin.py for it")


def test_a_table_naming_a_core_the_library_lacks_is_refused_where_it_is_written(asm_dir, host_lib):
    """Eagerly, at construction — not in the middle of a twin run, where the name would surface as
    whatever ctypes says about a missing symbol."""
    with pytest.raises(AttributeError, match="does not export"):
        AsmTwins(asm_dir, kit_smoke_project.IMAGE_SIZE,
                 callbacks={SUM_SLOT: DoorCallback("not_a_core", 1)}, lib=host_lib)


def test_a_table_without_a_library_is_refused(asm_dir, table):
    """...where a project with no table at all is fine: it has nothing to bind."""
    with pytest.raises(ValueError, match="needs the `lib`"):
        AsmTwins(asm_dir, kit_smoke_project.IMAGE_SIZE, callbacks=table)
    AsmTwins(asm_dir, kit_smoke_project.IMAGE_SIZE)


@pytest.mark.parametrize("attribute,value", [("ASM_STACK_BYTES", 0x200000),  # stack into the band
                                             ("IMAGE_ALIGN", 0x1000)])       # image below it
def test_a_band_that_would_collide_is_refused(monkeypatch, asm_dir, host_lib, table,
                                             attribute, value):
    """The band lives in the dead gap between the twin's stack top and the image. A bigger blob or a
    lower image would make a door address alias real memory — a twin would write where a callback is
    meant to be caught, or a callback would fire on an ordinary access — and neither leaves a trace
    anything else here could read. So it is asserted rather than assumed."""
    monkeypatch.setattr(asm_twin, attribute, value)
    with pytest.raises(AssertionError, match="does not lie strictly between"):
        AsmTwins(asm_dir, kit_smoke_project.IMAGE_SIZE, callbacks=table, lib=host_lib)


def test_a_twin_with_no_door_runs_exactly_as_it_always_has(asm_dir, image):
    """No callback table means no band, and everything about the run is what it was before the door
    existed: the twin computes, returns its answer and leaves the image alone."""
    twins = AsmTwins(asm_dir, kit_smoke_project.IMAGE_SIZE)
    out = twins.call(image, "probe_pure", 40, 2)
    assert out.d0 == 42
    assert out.image == image


def test_a_stub_reaching_the_band_refuses_even_with_no_table(asm_dir, image):
    """A project with no callback table can still have a blob full of door stubs — one twin gaining
    one arms nothing by itself. So `AsmTwins` arms the band either way, and the stub gets the named
    refusal rather than sixteen million instructions of zeros and a timeout naming nothing."""
    twins = AsmTwins(asm_dir, kit_smoke_project.IMAGE_SIZE)
    with pytest.raises(KeyError, match="no callback table entry declares"):
        twins.call(image, "probe_undeclared")


def test_run_bench_without_a_door_is_unchanged(asm_dir):
    """The kit-level contract underneath all of this, which the door did not move: `run_bench` with
    no band treats a PC inside it as ordinary memory — the zeros there decode and execute — and
    RAISES when the run does not reach the sentinel, exactly as it did before the door existed. That
    is what every non-twin caller (the perf tools, the model probes) still gets.

    Driven through `run_bench` rather than `AsmTwins.call` so the instruction cap can be small: the
    default is 16 million, and this twin would spend every one of them.
    """
    twins = AsmTwins(asm_dir, kit_smoke_project.IMAGE_SIZE)
    mem = bytearray(twins._template)      # the class's own layout, not a second derivation of it
    with pytest.raises(RuntimeError, match="did not return to the sentinel"):
        emu.run_bench(mem, twins.entry("probe_undeclared"), arg0=twins.image_at,
                      sp=twins.stack_top, sentinel=twins.sentinel, max_insns=SHRUNK_INSN_CAP)
