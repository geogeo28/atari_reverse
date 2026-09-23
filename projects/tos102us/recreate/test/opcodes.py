"""The 68000 as OPCODE BYTES — one home for every instruction word this project's cases assemble.

A case that has to stage machine code (a caller that builds an exception frame, a trampoline that
`rte`s into a handler, a routine the dispatch table is pointed at) writes it here as bytes, because
nothing in this project assembles 68000 at test time. A bare `b"\\x4e\\x75"` in the middle of a stub
is the worst shape that can take: it is right or wrong only to a reader who hand-decodes it, and it
was spelt in four batteries at once — `trap.py`, `isr.py`, `test_xbios_supexec.py` and
`test_xbios_initmous.py` each carried their own `RTS`.

So the words live here, named, with the instruction they encode beside them, and a stub reads as the
sequence it is. The values are `bytes` rather than ints because a stub is CONCATENATED: an operand is
appended with `trap.word()` / `trap.longword()`, and a `b"..."` constant joins without a `struct`
call per instruction.

NOT THE KIT'S `recreate_kit/stubs.py`, which holds a few private ints (`_RTS = 0x4E75`) for the
stubs it assembles with `struct.pack`. That is a different form for a different job — the kit's
stubs are whole routines it hands out, these are the words a project's own cases build with — and
the two are deliberately left apart rather than merged into one half-shared table.
"""

# ---- control ------------------------------------------------------------------------------------
RTS = b"\x4e\x75"
RTE = b"\x4e\x73"                       # ...the way out of an exception handler, and of a trampoline
TRAP_BIOS = b"\x4e\x4d"                 # trap    #13
TRAP_XBIOS = b"\x4e\x4e"                # trap    #14
TRAP_GEMDOS = b"\x4e\x41"                # trap    #1, the GEMDOS entry

# ---- the stack ----------------------------------------------------------------------------------
PUSH_WORD_IMMEDIATE = b"\x3f\x3c"       # move.w  #<imm>,-(sp)
PUSH_RETURN_PC = b"\x48\x7a"            # pea     <d16>(pc)
PUSH_SR = b"\x40\xe7"                   # move.w  sr,-(sp)
PUSH_STACK_LONG = b"\x2f\x2f"           # move.l  <d16>(sp),-(sp)
DROP_STACK_BYTES = b"\x4f\xef"          # lea     <d16>(sp),sp
SET_USER_STACK = b"\x4e\x60"            # move.l  a0,usp

# ---- loads and stores ---------------------------------------------------------------------------
# `move.l #<imm>,<register>` per register, keyed by the name a case's assertions use: a stub that
# scribbles on several of them writes them in a loop and reads them back by the same names.
LOAD_IMMEDIATE = {"d0": b"\x20\x3c", "d1": b"\x22\x3c", "d2": b"\x24\x3c",
                  "a0": b"\x20\x7c", "a1": b"\x22\x7c", "a2": b"\x24\x7c"}
# ...and the same instruction under the name a stub loading an ADDRESS reads better with. The 68000
# has one encoding for both (`movea.l #<imm>,a0` IS `move.l #<imm>,a0`), so this is an alias rather
# than a second constant — two spellings of one word is how they come to disagree.
LOAD_ADDRESS_IMMEDIATE = LOAD_IMMEDIATE["a0"]
STORE_A5_ABSOLUTE = b"\x23\xcd"         # move.l  a5,<xxx>.l
COPY_LONG_ABSOLUTE = b"\x23\xf9"        # move.l  <xxx>.l,<yyy>.l
