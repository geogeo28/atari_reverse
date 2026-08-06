"""Pin the HARNESS PLUMBING of the seeded PSG read model — `harness.differential`'s own code.

`test_psg_model.py` next door pins the MODEL: both implementations of it, driven directly from C.
What it cannot reach is the layer between them — `_seed_candidate_psg`, `_vet_psg_state`,
`_vet_psg_seed_reaches_the_path` — because those live in `harness`, which binds a project's compiled
candidate at import, and this directory deliberately binds no project.

So this file BUILDS one: a miniature "project" in a temp directory, whose `.PRG` is a hand-assembled
read-modify-write of the YM2149 mixer and whose candidate `.so` is `kit_candidate.c` plus the kit's
own `src/`. That is enough to run a real `harness.differential()` end to end, which is the one thing
the kit's suite has never been able to do.

WHAT IT PINS. The green case first — a correct reconstruction of an RMW passes with every surface
compared — and then the three things that would make that green meaningless:

  * `_vet_psg_state` catches a mutant candidate that NOTHING ELSE can. Both routines write no image
    byte at all, so with the comparison stubbed out the mutant passes the whole differential clean.
  * `_seed_candidate_psg` really seeds the candidate. Stubbed out, the same correct reconstruction
    reads a register it was never given and is refused.
  * a candidate missing the PSG ABI is refused by NAME while the oracle uses the path.

...plus both arms of the two-doors guard, which is about the CASE rather than the reconstruction: one
chip, two models, and an argument that stages the wrong one is silent without it.

The module skips whole when the shared oracle or a C compiler is absent — `oracle/build/` is
gitignored, so a bare checkout is a normal state to be in (`test_entry_state.py`'s convention).

BINDING IS PROCESS-WIDE AND ONE-SHOT: `recreate_kit.project.load` refuses a second project in one
process, so this is the only module in the kit's suite that may import `harness`, and the kit's own
`make test` runs serially for that reason.
"""
import atexit
import shutil
import struct
import subprocess
import sys
import tempfile

from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
ORACLE_SO = KIT / "oracle" / "build" / "liboracle.so"
CANDIDATE_SRC = Path(__file__).with_name("kit_candidate.c")

# The miniature project's geometry. image_size must equal os.h's OS_IMAGE_SIZE (harness vets it) and
# load_base must clear the poked-input block and leave the modeled heap and file-staging regions
# above the program — the ordinary layout every real project uses.
LOAD_BASE = 0x10000
IMAGE_SIZE = 0x100000

# The routine, in the form Wonder Boy's snd_psg_silence has it at $17f36 (TRAP_MODEL.md, Phase 6):
# select the mixer, read it back, merge the silence mask, write it back. `>H` words, big-endian.
PSG_SELECT = 0xFF8800
PSG_DATA = 0xFF8802
MIXER_REG = 7
SILENCE_MASK = 0x3F
PORT_DIR_BITS = 0xC0                  # what the case declares the chip held: port A/B direction
SILENCED = PORT_DIR_BITS | SILENCE_MASK
GIACCESS_REG = 14                     # PSG port A — the register Joust's floppy routine drives

_RMW_CODE = (struct.pack(">HHI", 0x13FC, MIXER_REG, PSG_SELECT)      # move.b #7,$ff8800.l
             + struct.pack(">HI", 0x1239, PSG_SELECT)                # move.b $ff8800.l,d1
             + struct.pack(">HH", 0x0001, SILENCE_MASK)              # ori.b #$3f,d1
             + struct.pack(">HI", 0x13C1, PSG_DATA)                  # move.b d1,$ff8802.l
             + struct.pack(">H", 0x4E75))                            # rts

# ...and a routine that reaches the SAME chip through the other door: XBIOS Giaccess(data, reg),
# pushed right to left so the shim reads data at caller+2 and reg at caller+4.
XBIOS_GIACCESS = 0x1C
_GIACCESS_CODE = (struct.pack(">HH", 0x3F3C, GIACCESS_REG)           # move.w #14,-(sp)   (reg)
                  + struct.pack(">HH", 0x3F3C, 0)                    # move.w #0,-(sp)    (data)
                  + struct.pack(">HH", 0x3F3C, XBIOS_GIACCESS)       # move.w #$1c,-(sp)  (fn)
                  + struct.pack(">H", 0x4E4E)                        # trap #14
                  + struct.pack(">HH", 0x4FEF, 6)                    # lea 6(sp),sp
                  + struct.pack(">H", 0x4E75))                       # rts

RMW_ENTRY = LOAD_BASE
GIACCESS_ENTRY = LOAD_BASE + len(_RMW_CODE)

PRG_MAGIC = 0x601A
PRG_HEADER = 28


def _build_prg(text):
    """A minimal GEMDOS .PRG carrying `text` and nothing else — no data, no bss, no relocations.

    The relocation table is one zero longword, which `prg_dis.parse_reloc` reads as "no fixups": the
    routines below are position-independent (absolute hardware addresses only), so there is nothing
    to relocate and the loader places the text verbatim at load_base.
    """
    header = struct.pack(">HIIIIIIH", PRG_MAGIC, len(text), 0, 0, 0, 0, 0, 0)
    return header + text + struct.pack(">I", 0)


def _write_project(root):
    """Lay out the miniature project: its .PRG, an empty name map, and a project.toml."""
    (root / "smoke.prg").write_bytes(_build_prg(_RMW_CODE + _GIACCESS_CODE))
    (root / "names.txt").write_text("")     # harness reads it for diff labels; nothing to name
    (root / "project.toml").write_text(
        'name = "kit_psg_smoke"\n'
        'prg = "smoke.prg"\n'
        'names = "names.txt"\n'
        'lib = "libkitsmoke.so"\n'
        f"load_base = {LOAD_BASE}\n"
        f"image_size = {IMAGE_SIZE}\n")


def _build_candidate(root):
    """Compile kit_candidate.c + the kit's own src/ into the project's candidate .so.

    Exactly what kit.mk builds for a real project (its SRC sweeps `$(KIT)/src/*.c`), so the ABI this
    exercises is the ABI a game gets — including the refusal tally and the Dosound ledger the harness
    requires or probes at import.
    """
    sources = sorted((KIT / "src").glob("*.c")) + [CANDIDATE_SRC]
    subprocess.run(
        ["cc", "-std=c11", "-O0", "-fPIC", "-shared", f"-I{KIT / 'include'}",
         *[str(src) for src in sources], "-o", str(root / "libkitsmoke.so")],
        check=True, capture_output=True, text=True)


def _bind():
    """Build and bind the miniature project, then import the harness against it.

    Module scope on purpose: `project.load` freezes the binding for the whole process, and `harness`
    derives module-level constants from it at import.
    """
    if not ORACLE_SO.exists():
        pytest.skip(f"{ORACLE_SO} is not built (gitignored) — "
                    f"run `make -C tools/recreate_kit oracle`", allow_module_level=True)
    if shutil.which("cc") is None:
        pytest.skip("no C compiler, so the miniature candidate cannot be built",
                    allow_module_level=True)
    root = Path(tempfile.mkdtemp(prefix="kit_psg_smoke_"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    _write_project(root)
    try:
        _build_candidate(root)
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"the miniature candidate did not compile: {exc.stderr}",
                    allow_module_level=True)

    sys.path.insert(0, str(KIT.parent))          # reverse/tools, so `recreate_kit` imports
    from recreate_kit import project             # noqa: E402
    project.load(root)
    # `recreate_kit.harness`, not a bare `import harness`: the kit's own module uses relative
    # imports, and each project's test/harness.py is the thin shim that re-exports it after binding
    # (projects/<game>/recreate/test/harness.py). This module IS that shim, for one throwaway
    # project — so it imports the package module directly rather than growing a second copy.
    from recreate_kit import harness as kit_harness   # noqa: E402  (importable only once bound)
    return kit_harness


harness = _bind()


def _rmw(glue_name, psg_seed=None, **kwargs):
    """Run the .PRG's read-modify-write against one of kit_candidate.c's glue functions."""
    return harness.differential(RMW_ENTRY, dict(kwargs),
                                lambda lib, buf: getattr(lib, glue_name)(buf),
                                psg_seed=psg_seed)


def test_a_correct_reconstruction_of_a_read_modify_write_is_green():
    """The whole plumbing, end to end: the same routine as 68000 code and as C, one seed handed to
    both sides, every off-image surface compared and equal.

    The image comparison contributes NOTHING here — both routines write zero image bytes, which is
    the situation the PSG surfaces exist for — so a green result is entirely the ledger's and the
    register file's word.
    """
    diffs, info = _rmw("g_psg_rmw", psg_seed={MIXER_REG: PORT_DIR_BITS})
    assert diffs == []
    assert info["regs"]["psg"] == [(MIXER_REG, SILENCED)], (
        "the oracle did not perform the read-modify-write, so nothing was compared")
    assert info["regs"]["psg_events"] == [
        (harness.OS_PSG_EVENT_READ, MIXER_REG, PORT_DIR_BITS),
        (harness.OS_PSG_EVENT_WRITE, MIXER_REG, SILENCED)], (
        "the oracle's access stream is not the read-then-write this case is about")


def test_the_mutant_that_only_the_psg_comparison_can_catch(monkeypatch):
    """`_vet_psg_state` is load-bearing, and this measures it rather than asserting it.

    `g_psg_rmw_skips_the_write` reads the mixer and never writes it back. With the comparison stubbed
    out the differential comes back GREEN — no diffs, no raise — because the routine's whole effect
    is off-image. Restore it and the same run reds. That gap IS the check's value.
    """
    monkeypatch.setattr(harness, "_vet_psg_state", lambda entry, o_regs: None)
    diffs, _ = _rmw("g_psg_rmw_skips_the_write", psg_seed={MIXER_REG: PORT_DIR_BITS})
    assert diffs == [], (
        "the mutant changed an image byte, so this case is not measuring the off-image comparison")

    monkeypatch.undo()
    with pytest.raises(AssertionError, match="direct-PSG access stream mismatch"):
        _rmw("g_psg_rmw_skips_the_write", psg_seed={MIXER_REG: PORT_DIR_BITS})


def test_the_candidate_is_really_seeded_before_it_runs(monkeypatch):
    """`_seed_candidate_psg` is load-bearing too: without it the candidate reads a register nothing
    declared, refuses through `os_refused()`, and `_vet_no_os_refusal` throws the case away.

    That is the failure a one-sided seed produces — the oracle served the read, the candidate did
    not — and it is exactly what "refusing on ONE side is a false green" is about, caught rather than
    passed.

    The candidate's chip state is cleared first, by the very call being stubbed out: it is
    process-global, so without that the run would inherit whatever the previous case left in it and
    the failure would depend on test order rather than on the missing seed.
    """
    harness._seed_candidate_psg(None)
    monkeypatch.setattr(harness, "_seed_candidate_psg", lambda psg_seed: None)
    with pytest.raises(AssertionError, match=r"os_\* call\(s\) the TOS model REFUSES"):
        _rmw("g_psg_rmw", psg_seed={MIXER_REG: PORT_DIR_BITS})


def test_a_candidate_without_the_psg_abi_is_refused_by_name(monkeypatch):
    """The optional-ABI arm. A candidate built outside kit.mk exports no `src/psg.c` symbols, and is
    served only while the oracle never touches the path — so the moment it does, the refusal must
    name the symbols that are missing rather than leave the reader guessing which of seven they are.
    """
    monkeypatch.setattr(harness, "_has_psg_ledger", False)
    monkeypatch.setattr(harness, "_missing_psg_ledger", ["g_psg_log_kinds"])
    with pytest.raises(AssertionError, match="exports no g_psg_log_kinds"):
        _rmw("g_psg_untouched", psg_seed={MIXER_REG: PORT_DIR_BITS})


def test_seeding_both_doors_of_the_chip_at_once_is_refused():
    """One chip, two models. `psg_seed=` declares the direct path's off-image register file;
    `psg_regs()` stages the in-image file XBIOS Giaccess reads. Declaring both in one case says the
    chip held two different things, in two models that never see each other's stores.
    """
    with pytest.raises(AssertionError, match="TWO doors"):
        _rmw("g_psg_rmw", psg_seed={MIXER_REG: PORT_DIR_BITS},
             _pokes=harness.psg_regs({MIXER_REG: PORT_DIR_BITS}))


def test_a_seed_the_run_cannot_read_while_it_drives_giaccess_is_refused():
    """The other arm, and the one a real case gets wrong: the seed is installed, the routine reaches
    the chip through the TRAP instead, and nothing reads the declaration. Silent without this —
    the case passes while testing the read-back it meant to stage not at all.
    """
    with pytest.raises(AssertionError, match="reaches the chip through the TRAP path"):
        harness.differential(GIACCESS_ENTRY, {}, lambda lib, buf: lib.g_psg_untouched(buf),
                             psg_seed={GIACCESS_REG: PORT_DIR_BITS})


def test_a_run_under_a_capture_it_did_not_ask_for_is_refused():
    """The one-sided capture. `emu.audio_capture` is an ORACLE-GLOBAL toggle, so a run can be served
    the mode's fabricated answers without ever asking — a block that raised on its way out, an
    extractor sharing the process, a bare `audio_capture(True)` someone forgot. Armed, this same
    routine's `$ff8800` read of a register nothing declared is answered 0 instead of refused, which
    is exactly the false green the seeded model exists to close.

    `harness.differential` already vets the mode off, but most PSG cases call `emu.run` directly, so
    the refusal belongs there too. `audio_capturing()` is what declares the intent — the positive
    half below, so this is a pair rather than a one-way assertion.
    """
    emu = harness.emu
    emu.audio_capture(True)
    try:
        with pytest.raises(RuntimeError, match="did not opt into it"):
            emu.run(harness.make_image(), RMW_ENTRY)
    finally:
        emu.audio_capture(False)

    with emu.audio_capturing():
        _, _, out_regs = emu.run(harness.make_image(), RMW_ENTRY)
    assert out_regs["psg"] == [(MIXER_REG, SILENCE_MASK)], (
        "inside the manager the same run is served, and from a cleared file — so the read-back is "
        "the mode's fabricated 0 and `ori.b #$3f` yields $3f, which is what makes it fabricated")


def test_a_seed_no_run_reads_is_left_alone_when_neither_door_was_used():
    """The limit of the guard above, stated as a case so it cannot be tightened by accident.

    An over-declared input is ordinary — a case may seed a register the branch it takes never reads —
    and refusing that would make `psg_seed` a claim about control flow rather than about the chip.
    Only a seed contradicted by the OTHER door being used is refused.
    """
    diffs, info = _rmw("g_psg_rmw", psg_seed={MIXER_REG: PORT_DIR_BITS, GIACCESS_REG: 0x07})
    assert diffs == []
    assert info["regs"]["psg_giaccess"] == 0, "the run used the trap path, so this proves nothing"
