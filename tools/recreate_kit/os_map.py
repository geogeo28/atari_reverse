"""The harness-poked input block (``include/os.h``, 0x600..0x61f) and the overlap questions the
kit's guards ask about it.

It has a module of its own — rather than sitting with the rest of the ``os.h`` mirror in
``harness.py`` — for two reasons:

* **two importers.** ``oracle/emu.py`` needs the block's extent for the per-run guard
  (``_vet_no_poked_input_read``) and ``harness.py`` needs the individual addresses for the pokes it
  builds. A constant defined in one of them and imported by the other would make the pair circular.
* **it must be importable with nothing built.** ``emu`` and ``harness`` each load a compiled ``.so``
  at import, so neither can be exercised by the kit's own suite, which runs in a bare checkout
  (``tools/recreate_kit/Makefile``). Everything here is plain arithmetic over explicit arguments, so
  ``test/test_os_map.py`` can pin it directly — which is what stops the shared kit's protection from
  living entirely inside one project's tests.

``test/test_os_memory_map.py`` pins every constant below equal to ``include/os.h``.
"""

# ---- the harness-poked model state (mirror of include/os.h, "harness-poked model state") ----
# Hardware whose real value is time-varying is an ordinary in-image test input, so both cores read
# the same bytes. See TRAP_MODEL.md, "The harness-poked model state".
OS_CON_PENDING = 0x600       # u32: nonzero = a character is waiting at the console (Bconstat)
OS_CON_CHAR = 0x604          # u32: the longword Bconin returns (scancode << 16 | ascii)
OS_RANDOM_VALUE = 0x608      # u32: what XBIOS Random returns (masked to 24 bits)
OS_PSG_REGS = 0x610          # the YM2149 register file that XBIOS Giaccess reads and writes
OS_PSG_NREGS = 16
OS_PSG_WRITE = 0x80          # bit 7 of Giaccess's register argument selects write over read
OS_POKE_BLOCK_END = OS_PSG_REGS + OS_PSG_NREGS   # first address above the poked block (0x620)

# ---- the direct-PSG ledger's event kinds (mirror of include/os.h, "Phase 6") ----
# NOT poked-input state — they live here for this module's OTHER reason: `emu.psg_events` tags each
# entry with one and `harness._vet_psg_state` compares them, and emu cannot import harness. The
# ordered stream carries reads as well as writes, so that a reconstruction reading the WRONG
# register is separable from a correct one — its writes are not.
OS_PSG_EVENT_WRITE = 0
OS_PSG_EVENT_READ = 1


def poked_input_overlaps_program(load_base, program_end):
    """Does the poked-input block intersect a program loaded at ``[load_base, program_end)``?

    True only for a program loaded below ``OS_POKE_BLOCK_END`` — which no project can avoid when the
    game runs at a fixed low address (``projects/wonderboy`` runs at 0x400, and below that is the
    68000 vector page). While it holds, every poke into the block writes the game's own code, and
    every trap that reads the block reads the game's own code, on BOTH sides — so the guards keyed on
    this predicate are what keep such a run from coming back green while proving nothing.

    ``program_end`` is None until a program has been loaded (``loader.PROGRAM_END``); there is
    nothing to collide with then, so the answer is False.
    """
    return (program_end is not None
            and load_base < OS_POKE_BLOCK_END and OS_CON_PENDING < program_end)


def poke_hits_poked_input(addr, length):
    """Does a poke of ``length`` bytes at ``addr`` touch any part of the poked-input block?

    Keyed on the RANGE, not on which builder produced it: ``harness.console_key()`` and
    ``harness.psg_regs()`` are only two of the three kinds of state the block holds — there is no
    builder for ``OS_RANDOM_VALUE``, so hand-writing the address into a poke dict is the only way any
    project stages one, and that idiom is in use (``projects/joust/recreate/test/test_os_traps.py``).

    A zero-length poke writes nothing and so hits nothing; said explicitly because the half-open
    intersection below is degenerate for an empty range and would otherwise answer True for every
    ``addr`` above the block's start.
    """
    return length > 0 and addr < OS_POKE_BLOCK_END and OS_CON_PENDING < addr + length
