"""THE SHIPPED CONFIGURATION'S GLUE — one thunk per transcribed C core that other C calls.

    python bench/shipped_glue.py build/bench_shipped/glue.S     # run by the Makefile's shipped-blob rule

A shipped ROM does not link the C twin of a routine it takes as the ROM's own instructions
(`include/vdi/transcribed.h`): C that calls such a core reaches the `.S` entry instead, through glue that
turns a GCC call into the entry's own contract. This writes that glue, GENERATED rather than typed, so the
second Tier 3 blob (`build/bench_shipped/`) measures the callers as they would ship. The file is a thunk
NAMED AFTER each core `test/vdi.py`'s C_CALLERS_OF_TRANSCRIBED_CORES lists — the blob's build makes each
core WEAK (`TRANSCRIBED_CORE`), so the thunk is what every call links to. A thunk saves
the callee-saved registers the table's row says the entry changes (and any it loads an argument into),
moves the C arguments where the entry reads them, `jsr`s the entry and restores. Three shapes, by what the
core's routine is declared as:

  * a REGISTER contract (`vdi.declare_primitive`): each argument register loaded from its C slot, D0
    answered as the entry leaves it (the image-only primitives are this shape with no arguments);
  * an ALCYON call (`vdi.declare_alcyon`): the GCC longword slots repacked into the WORD and LONG frame an
    Alcyon caller pushes, and popped after;
  * a VDI FUNCTION (an `_OPCODE` sibling in `addrs.h`): entered with nothing, as the dispatcher does.

THE FILE IS WRITTEN ONLY WHEN ITS TEXT CHANGES, so the blob relinks when the glue does and not whenever a
test file it imports is edited (the Makefile's `snapshot-inputs` arrangement).
"""
import sys
from pathlib import Path

RECREATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECREATE.parents[2] / "tools"))     # reverse/tools — the shared recreate kit
sys.path.insert(0, str(RECREATE / "test"))                 # ...and the declarations the thunks derive from

from recreate_kit import project                           # noqa: E402
project.load(RECREATE)

from harness import addrs                                  # noqa: E402
# Every battery, so every register contract and Alcyon signature is declared before a thunk asks for one.
import test_boot_snapshot                                  # noqa: E402,F401
import vdi                                                 # noqa: E402

# The GCC m68k ABI's callee-saved registers, in `movem`'s list order: what a thunk owes its C caller.
CALLEE_SAVED = ("d2", "d3", "d4", "d5", "d6", "d7", "a2", "a3", "a4", "a5", "a6")
RETURN_ADDRESS_BYTES = vdi.LONG_BYTES
SLOT_BYTES = vdi.LONG_BYTES             # every GCC argument slot, a promoted `int16_t` included
WORD_IN_SLOT = SLOT_BYTES - vdi.WORD_BYTES      # ...whose value is the slot's LOW word: big-endian


def _register_list(registers):
    return "/".join(f"%{register}" for register in registers)


def _save(registers):
    return [f"    movem.l {_register_list(registers)},-(%sp)"] if registers else []


def _restore(registers):
    return [f"    movem.l (%sp)+,{_register_list(registers)}"] if registers else []


def _slot(index, saved):
    """Where C argument `index` is, from the thunk's SP after its `movem` of `saved` registers."""
    return RETURN_ADDRESS_BYTES + len(saved) * vdi.LONG_BYTES + index * SLOT_BYTES


def _register_body(entry, contract):
    """Each argument register loaded from its C slot — the image is slot 0, the registers follow in the
    contract's order — round the `jsr`. A several-register answer would need writing back through the
    core's `results` pointer; no C caller reaches such a core, so it is refused rather than guessed."""
    if len(contract.results) > 1:
        raise NotImplementedError(f"{entry} answers in {contract.results}: no thunk shape writes those back")
    saved = [register for register in CALLEE_SAVED
             if register in vdi.TRANSCRIBED[entry] or register in contract.arguments]
    loads = [f"    move{'a' if register.startswith('a') else ''}.l {_slot(index + 1, saved)}(%sp),%{register}"
             for index, register in enumerate(contract.arguments)]
    return [*_save(saved), *loads, f"    jsr     {entry}", *_restore(saved)]


def _alcyon_body(entry, signature):
    """The GCC slots re-pushed as the Alcyon frame, last argument first, and dropped after the `jsr`."""
    saved = [register for register in CALLEE_SAVED if register in vdi.TRANSCRIBED[entry]]
    first_framed = len(signature.argtypes) - len(vdi.frame_argtypes(vdi.transcription_routine(entry)))
    pushes, pushed = [], 0
    for index in reversed(range(first_framed, len(signature.argtypes))):
        width = vdi.ARG_BYTES[signature.argtypes[index]]
        at = _slot(index, saved) + pushed + (WORD_IN_SLOT if width == vdi.WORD_BYTES else 0)
        pushes.append(f"    move.{'w' if width == vdi.WORD_BYTES else 'l'} {at}(%sp),-(%sp)")
        pushed += width
    return [*_save(saved), *pushes, f"    jsr     {entry}", f"    lea     {pushed}(%sp),%sp", *_restore(saved)]


def _function_body(entry):
    saved = [register for register in CALLEE_SAVED if register in vdi.TRANSCRIBED[entry]]
    return [*_save(saved), f"    jsr     {entry}", *_restore(saved)]


def thunk(core):
    """The glue that answers a C call of `core` by entering its `.S`."""
    entry = vdi.TRANSCRIBED_CORES[core]
    routine = vdi.transcription_routine(entry)
    if routine in vdi.PRIMITIVES:
        body, shape = _register_body(entry, vdi.PRIMITIVES[routine]), "register contract"
    elif routine in vdi.ALCYON:
        body, shape = _alcyon_body(entry, vdi.ALCYON[routine]), "Alcyon frame"
    elif hasattr(addrs, routine + "_OPCODE"):
        body, shape = _function_body(entry), "VDI function"
    else:
        raise LookupError(f"{routine} is transcribed and called from C, but declares no contract a thunk "
                          f"could follow — `vdi.declare_primitive` or `vdi.declare_alcyon` it")
    # `.type`/`.size` so the symbol table SIZES each thunk: Tier 3's glue rule (T→G) counts the cycles spent
    # inside exactly these bytes (`bench/tier3.py`, `glue_ranges`), and a disassembly stops at the thunk's end.
    return [f"/* {core} -> {entry}: {shape} */", f"    .globl  {core}", f"    .type   {core},@function", f"{core}:",
            *body, "    rts", f"    .size   {core},.-{core}", ""]


def glue_text(cores):
    header = ["/* GENERATED by bench/shipped_glue.py — the shipped configuration's glue: each C call of a",
              " * transcribed core enters its `.S` (include/vdi/transcribed.h). Do not edit. */",
              "    .text", ""]
    return "\n".join(header + [line for core in cores for line in thunk(core)])


def thunked_cores():
    """Every core the glue carries a thunk for, in the file's order: each one some C calls."""
    return sorted({core for _caller, core in vdi.C_CALLERS_OF_TRANSCRIBED_CORES})


def main(argv):
    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    text = glue_text(thunked_cores())
    if not out.exists() or out.read_text() != text:
        out.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
