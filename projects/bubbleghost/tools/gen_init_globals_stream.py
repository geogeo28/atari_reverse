#!/usr/bin/env python3
"""Derive `init_globals` @ 0x16d8e's instruction stream from the disassembly, as a C table.

    python3 projects/bubbleghost/tools/gen_init_globals_stream.py \
        > projects/bubbleghost/recreate/include/init_globals_stream.h

WHY A GENERATOR. `init_globals` is 7,869 straight-line stores with no branch, no loop and no call —
every non-zero initialiser of this program's 0x6650-byte BSS, written one `move` at a time (which is
why `strings` finds "GHOST.LOA" in no file). Transcribing that by hand would be 7,869 chances to
mistype a word, so `recreate/src/init.c` is a ten-case interpreter over the stream and the stream
itself is decoded from `out/prg_dis.txt`.

WHY IT IS DERIVED FROM THE ASM AND NOT FROM THE IMAGE. `recreate/test/conftest.py`'s post-init
fixture IS this routine's own output, and every differential case in the project runs on it — so a
reconstruction read off that image would be a tautology, green about nothing.

TWO THINGS MAKE THE OUTPUT TRUSTWORTHY, and both are refusals rather than checks that can pass
quietly: any instruction outside the ten shapes below aborts the run by name, and the decoded stream
is SIMULATED and compared against an oracle run of the real routine over the whole image (minus the
harness's stack band) before a single line is written.

Re-run it whenever `out/prg_dis.txt` is re-cut or the load base moves; the header it writes says
"GENERATED; do not edit by hand" and means it.
"""
import argparse
import collections
import re
import sys
from pathlib import Path

REVERSE = Path(__file__).resolve().parents[3]
PROJECT = REVERSE / "projects" / "bubbleghost"
DISASSEMBLY = PROJECT / "out" / "prg_dis.txt"
RECREATE = PROJECT / "recreate"

A4_BASE = 0x24f1a          # the BSS/DATA boundary every global is `n(a4)` from (README, image model)
LOAD_BASE = 0x10000        # ...and `p_tbase`, which is the A5 the routine's last paragraph reads
ENTRY = 0x16d8e            # `lea -7308(a4),a1`
RTS = 0x1e8c8              # the last instruction of TEXT, and this routine's only exit
MAX_INSNS = 50_000

Step = collections.namedtuple("Step", "op a b")


def _signed_word(value):
    return value - 0x10000 if value >= 0x8000 else value


def read_instructions(path):
    """[(address, text)] for the routine's own instructions, in address order."""
    rows = []
    for line in path.read_text().splitlines():
        m = re.match(r"^01([0-9a-f]{4}): ([0-9a-f]+)\s+(.*?)\s*$", line)
        if not m:
            continue
        address = int(m.group(1), 16) + LOAD_BASE
        if ENTRY <= address < RTS:
            rows.append((address, m.group(3)))
    rows.sort()
    if not rows or rows[0][0] != ENTRY:
        sys.exit(f"{path}: no instruction at {ENTRY:#x} — is this the right disassembly?")
    return rows


def decode(rows):
    """The ten shapes, and a REFUSAL for anything else.

    `lea n(a5),a0` + `move.l a0,(a1)+` is the one pair that collapses to a single step; every other
    instruction is one.
    """
    steps, pending_a5 = [], None
    for address, text in rows:
        m = re.fullmatch(r"lea (-?\d+)\(a4\),a1", text)
        if m:
            steps.append(Step("AT", A4_BASE + int(m.group(1)), 0))
            continue
        m = re.fullmatch(r"lea (\d+)\(a5\),a0", text)
        if m:
            pending_a5 = int(m.group(1))
            continue
        if text == "move.l a0,(a1)+":
            if pending_a5 is None:
                sys.exit(f"{address:#x}: `move.l a0,(a1)+` with no `lea n(a5),a0` before it")
            steps.append(Step("A5", pending_a5, 0))
            pending_a5 = None
            continue
        m = re.fullmatch(r"adda\.w #\$([0-9a-f]+),a1", text)
        if m:
            steps.append(Step("SKIP", _signed_word(int(m.group(1), 16)), 0))
            continue
        m = re.fullmatch(r"move\.([bwl]) #\$([0-9a-f]+),\(a1\)\+", text)
        if m:
            steps.append(Step({"b": "B", "w": "W", "l": "L"}[m.group(1)], int(m.group(2), 16), 0))
            continue
        m = re.fullmatch(r"move\.([bwl]) #\$([0-9a-f]+),(-?\d+)\(a4\)", text)
        if m:
            steps.append(Step({"b": "SETB", "w": "SETW", "l": "SETL"}[m.group(1)],
                              A4_BASE + int(m.group(3)), int(m.group(2), 16)))
            continue
        m = re.fullmatch(r"move\.l (-?\d+)\(a4\),(-?\d+)\(a4\)", text)
        if m:
            steps.append(Step("COPY", A4_BASE + int(m.group(2)), A4_BASE + int(m.group(1))))
            continue
        sys.exit(f"{address:#x}: {text!r} is not one of this routine's ten shapes — the stream has "
                 f"changed, and the interpreter in recreate/src/init.c has to change with it")
    if pending_a5 is not None:
        sys.exit("the stream ends with a `lea n(a5),a0` nothing stores")
    return steps


def simulate(steps, image, text_base):
    """Run the decoded stream over a copy of `image`, exactly as `src/init.c`'s interpreter does."""
    memory, cursor = bytearray(image), 0
    for op, a, b in steps:
        if op == "AT":
            cursor = a
        elif op == "SKIP":
            cursor = (cursor + a) & 0xffffffff
        elif op == "B":
            memory[cursor] = a & 0xff
            cursor += 1
        elif op == "W":
            memory[cursor:cursor + 2] = (a & 0xffff).to_bytes(2, "big")
            cursor += 2
        elif op == "L":
            memory[cursor:cursor + 4] = (a & 0xffffffff).to_bytes(4, "big")
            cursor += 4
        elif op == "A5":
            memory[cursor:cursor + 4] = ((text_base + a) & 0xffffffff).to_bytes(4, "big")
            cursor += 4
        elif op == "SETB":
            memory[a] = b & 0xff
        elif op == "SETW":
            memory[a:a + 2] = (b & 0xffff).to_bytes(2, "big")
        elif op == "SETL":
            memory[a:a + 4] = (b & 0xffffffff).to_bytes(4, "big")
        elif op == "COPY":
            memory[a:a + 4] = memory[b:b + 4]
        else:
            sys.exit(f"the simulator has no case for {op}")
    return bytes(memory)


def check_against_the_oracle(steps):
    """Refuse to emit a stream whose effect is not the routine's, byte for byte.

    Compared below the harness's stack guard: the oracle writes its own sentinel return address at
    the top of the image, and the interpreter has no machine stack to write one on.
    """
    sys.path.insert(0, str(RECREATE / "test"))
    import abi                    # noqa: E402  (the project's own harness shim puts the kit on the path)
    import emu                    # noqa: E402
    import harness                # noqa: E402

    oracle, _writes, _regs = emu.run(harness.BASE_IMAGE, ENTRY,
                                     regs={"a4": abi.A4_BASE, "a5": LOAD_BASE},
                                     max_insns=MAX_INSNS)
    ours = simulate(steps, harness.BASE_IMAGE, LOAD_BASE)
    differing = [at for at in range(emu.STACK_GUARD_LO) if ours[at] != oracle[at]]
    if differing:
        sys.exit(f"the decoded stream and the real routine differ at {len(differing)} byte(s), the "
                 f"first at {differing[0]:#x} — the decoder is wrong, not the header")
    return len(differing)


HEADER = '''/* init_globals_stream.h — `init_globals` @ 0x16d8e AS DATA. GENERATED; do not edit by hand.
 *
 * Written by `projects/bubbleghost/tools/gen_init_globals_stream.py`, which decodes the routine's
 * instruction stream out of `../out/prg_dis.txt`, refuses anything outside the ten shapes below,
 * and checks its own output against an oracle run before emitting a line. Re-run it if the
 * disassembly is re-cut or the load base moves.
 *
 * WHAT THIS IS. The routine is 7,869 straight-line instructions with no branch, no loop and no call
 * — every non-zero initialiser of this program's 0x6650-byte BSS, written one `move` at a time,
 * which is why `strings` finds "GHOST.LOA" nowhere in the .PRG. `src/init.c`'s `init_globals` is
 * the ten-case interpreter over the table below.
 *
 * WHY IT IS DERIVED FROM THE ASM AND NOT FROM THE IMAGE. `test/conftest.py`'s post-init fixture is
 * this routine's own output, and every differential case in the project runs on it — so a
 * reconstruction read off that image would be a tautology, green about nothing.
 *
 * THE SHAPES, each one instruction of the original (the `lea n(a5),a0 / move.l a0,(a1)+` pair at
 * the tail is the one that collapses to a single step):
 *
 *   AT(addr)        `lea n(a4),a1`             — point the cursor at an absolute address
 *   SKIP(n)         `adda.w #n,a1`             — step it, as a SIGNED word
 *   B/W/L(v)        `move.X #v,(a1)+`          — store and advance
 *   A5(n)           `lea n(a5),a0 / move.l a0,(a1)+`  — a pointer INTO THE PROGRAM'S OWN TEXT
 *   SETB/SETW/SETL(addr, v)  `move.X #v,n(a4)` — store to a named global, cursor untouched
 *   COPY(dst, src)  `move.l n(a4),m(a4)`       — one longword of DATA into a BSS slot
 */
#ifndef BG_INIT_GLOBALS_STREAM_H
#define BG_INIT_GLOBALS_STREAM_H

#include <stdint.h>

typedef enum {
    IG_CURSOR, IG_ADVANCE, IG_PUT_B, IG_PUT_W, IG_PUT_L, IG_PUT_A5,
    IG_SET_B, IG_SET_W, IG_SET_L, IG_COPY_L
} InitGlobalsOp;

typedef struct {
    uint8_t  op;
    uint32_t a;      /* an address, a store's destination, or the value stored */
    uint32_t b;      /* the value, for the two-field shapes; 0 otherwise */
} InitGlobalsStep;

#define AT(addr)       {IG_CURSOR,   (addr), 0}
#define SKIP(n)        {IG_ADVANCE,  (uint32_t)(int32_t)(n), 0}
#define B(v)           {IG_PUT_B,    (v), 0}
#define W(v)           {IG_PUT_W,    (v), 0}
#define L(v)           {IG_PUT_L,    (v), 0}
#define A5(n)          {IG_PUT_A5,   (n), 0}
#define SETB(addr, v)  {IG_SET_B,    (addr), (v)}
#define SETW(addr, v)  {IG_SET_W,    (addr), (v)}
#define SETL(addr, v)  {IG_SET_L,    (addr), (v)}
#define COPY(dst, src) {IG_COPY_L,   (dst), (src)}

static const InitGlobalsStep INIT_GLOBALS_STREAM[] = {
'''

FOOTER = '''};

#define INIT_GLOBALS_STEPS (sizeof INIT_GLOBALS_STREAM / sizeof INIT_GLOBALS_STREAM[0])

#undef AT
#undef SKIP
#undef B
#undef W
#undef L
#undef A5
#undef SETB
#undef SETW
#undef SETL
#undef COPY

#endif /* BG_INIT_GLOBALS_STREAM_H */
'''

STEPS_PER_LINE = 8


def emit(steps, out):
    out.write(HEADER)
    line = []
    for op, a, b in steps:
        if op in ("SETB", "SETW", "SETL", "COPY"):
            line.append(f"{op}({a:#x},{b:#x})")
        elif op == "SKIP":
            line.append(f"SKIP({a})")
        else:
            line.append(f"{op}({a:#x})")
        if len(line) == STEPS_PER_LINE:
            out.write("    " + " ".join(item + "," for item in line) + "\n")
            line = []
    if line:
        out.write("    " + " ".join(item + "," for item in line) + "\n")
    out.write(FOOTER)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", type=Path,
                        help="write here instead of stdout (the header's home is "
                             "recreate/include/init_globals_stream.h)")
    parser.add_argument("--no-check", action="store_true",
                        help="skip the oracle comparison. ONLY for a machine with no built "
                             "harness; the check is what makes the output trustworthy")
    args = parser.parse_args()

    rows = read_instructions(DISASSEMBLY)
    steps = decode(rows)
    print(f"{len(rows)} instructions -> {len(steps)} steps", file=sys.stderr)
    if not args.no_check:
        check_against_the_oracle(steps)
        print("stream verified against an oracle run: 0 differing bytes", file=sys.stderr)

    if args.output:
        with args.output.open("w") as out:
            emit(steps, out)
    else:
        emit(steps, sys.stdout)


if __name__ == "__main__":
    main()
