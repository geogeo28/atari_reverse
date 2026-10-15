"""Pin the oracle's LINE-F EXCEPTION over every `$Fxxx` word: the CPU is a 68000, so each one traps.

Upstream Musashi executes `$F620..$F627` as the 68040's `MOVE16 (Ax)+,(Ay)+` whatever CPU type it is
set to — its handler is the one Line-F handler that does not ask — and the oracle carries the missing
guard (`oracle/move16_guard.c`). A 68000 takes every `$Fxxx` word as an exception through vector 11:
the six-byte group-1/2 frame (the status word, then the word's OWN address) on the supervisor stack,
the PC loaded from the vector, in 34 cycles, the word itself executed not at all. Each word is run alone
with vector 11 pointing at the sentinel, so the run stops at the handler's first instruction with the
frame just pushed — and a word the CPU EXECUTES instead jumps to the sentinel behind it, no frame pushed.

The step count cannot tell the two apart (an executed word plus the `jmp` behind it is also one step
past the reset's), so what says "not executed" is the address-register file: MOVE16 post-increments
both of its registers by sixteen, and a trap leaves every one as the run was seeded.

The guard is installed after `m68k_init()`, which builds the table on a process's FIRST run only — a
guard installed before it would be overwritten for that one run and hold for every later one, which
no case of a pytest worker is sure to see. So one case runs `$F620` as a fresh process's first run.
"""
import json
import struct
import subprocess
import sys
import textwrap
from pathlib import Path

import kit_smoke_project

kit_smoke_project.bind()

import emu           # noqa: E402  (importable only once a project is bound)

PROBE_AT = 0x20000                    # the word under test, above the vector page and the poked block
VECTOR_LINE_F = 0x2C                  # vector 11, the Line-F emulator's
LINE_F_WORDS = range(0xF000, 0x10000)
FIRST_MOVE16_WORD = 0xF620            # `MOVE16 (A0)+,(Ay)+`, the first of the eight the guard covers
JMP_ABSOLUTE = 0x4EF9                 # jmp <xxx>.l
# ...behind the word: a word EXECUTED as MOVE16 takes the zero as its extension word (to (A0)+) and
# jumps to the sentinel, so it ends there with no frame pushed — whatever it did to the stack
# pointer — rather than running on.
AFTER_THE_WORD = struct.pack(">HHI", 0, JMP_ABSOLUTE, emu.SENTINEL)
LINE_F_FRAME = struct.Struct(">HI")   # the status word, the PC: a 68000's group-1/2 exception frame
ENTRY_STATUS = 0x2700                 # shim.c's ENTRY_SR: supervisor, interrupts masked
LINE_F_CYCLES_68000 = 34              # Musashi's exception cycle table, 68000 column, vector 11
# A bench run's counters include the shim's first step after its reset, which spends the reset's own
# cycles and executes no instruction (shim.c, osh_run's loop; test_sched_model.py).
RESET_STEP_CYCLES = 40
# The entry file: each address register a distinct, 16-byte-aligned address in mapped RAM above the
# probe, so an executed MOVE16 reads and writes real memory and moves the register it used.
SEEDED_AT = 0x30000
SEEDED_STRIDE = 0x100
ADDRESS_REGS = [name for name in emu.REPORTED_REGS if name.startswith("a")]   # a0..a6: shim.c reports no a7
SEEDED_AREGS = {name: SEEDED_AT + n * SEEDED_STRIDE for n, name in enumerate(ADDRESS_REGS)}
SEED = [SEEDED_AREGS.get(name, 0) for name in emu.REPORTED_REGS]
EXPECTED = (LINE_F_FRAME.pack(ENTRY_STATUS, PROBE_AT), 1 + 1, RESET_STEP_CYCLES + LINE_F_CYCLES_68000, SEEDED_AREGS)


def _line_f_image():
    image = bytearray(kit_smoke_project.IMAGE_SIZE)
    image[VECTOR_LINE_F:VECTOR_LINE_F + 4] = struct.pack(">I", emu.SENTINEL)
    image[PROBE_AT + 2:PROBE_AT + 2 + len(AFTER_THE_WORD)] = AFTER_THE_WORD
    return image


def _taken(word):
    """`(frame bytes, steps, cycles, address registers)` of one run of `word` alone at PROBE_AT, the
    reset's step included — on an image of its own, so a word the CPU executes cannot reach the next
    word's run."""
    image = _line_f_image()
    image[PROBE_AT:PROBE_AT + 2] = struct.pack(">H", word)
    frame_at = emu.STACK_TOP - LINE_F_FRAME.size
    result = emu.run_bench(image, PROBE_AT, arg0=0, sp=emu.STACK_TOP, sentinel=emu.SENTINEL, seed_regs=SEED)
    assert result["reached"], f"{word:#06x}: the run did not stop at the sentinel"
    left = {name: result["regs"][name] for name in SEEDED_AREGS}
    return bytes(image[frame_at:emu.STACK_TOP]), result["ninsns"], result["cycles"], left


def test_every_line_f_word_takes_vector_11_with_the_68000_s_frame_and_cost():
    wrong = {word: taken for word in LINE_F_WORDS if (taken := _taken(word)) != EXPECTED}
    assert not wrong, {f"{word:#06x}": taken for word, taken in sorted(wrong.items())[:16]}


def test_a_process_s_first_run_already_traps_the_first_move16_word():
    """In a subprocess because this worker has run the oracle already, and its table is long built."""
    script = textwrap.dedent(f"""
        import json, sys
        sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})
        import test_line_f
        frame, steps, cycles, left = test_line_f._taken({FIRST_MOVE16_WORD})
        print(json.dumps([frame.hex(), steps, cycles, left]))
    """)
    out = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    frame, steps, cycles, left = json.loads(out.stdout.strip().splitlines()[-1])
    assert (bytes.fromhex(frame), steps, cycles, left) == EXPECTED
