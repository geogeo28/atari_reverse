"""The harness-poked input block (``include/os.h``, ``OS_CON_PENDING``..``OS_POKE_BLOCK_END``) and
the overlap questions the kit's guards ask about it.

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
OS_CON_PENDING = 0x600       # u32: how many keystrokes are queued, up to OS_CON_QUEUE_MAX (nonzero
                             # = one is waiting; a larger value is the older flag spelling and is
                             # served as a single key — see include/os.h's os_console_take_key)
OS_CON_CHAR = 0x604          # u32: the longword the NEXT console read returns (scancode<<16 | ascii)
OS_RANDOM_VALUE = 0x608      # u32: what XBIOS Random returns (masked to 24 bits)
OS_PSG_REGS = 0x610          # the YM2149 register file that XBIOS Giaccess reads and writes
OS_PSG_NREGS = 16
OS_PSG_WRITE = 0x80          # bit 7 of Giaccess's register argument selects write over read
# The VDI's two input devices, and the workstation state its attribute calls keep. All three are in
# the block for the same reason the console key is: they are read and written by os.h on BOTH sides,
# so under a program that covers these addresses they are the GAME's bytes and every guard keyed on
# the block has to apply to them unchanged. See include/os.h, "the VDI WORKSTATION STATE".
OS_MOUSE = 0x620             # three words: x, y, buttons (vq_mouse)
OS_MOUSE_OFF_X = 0
OS_MOUSE_OFF_Y = 2
OS_MOUSE_OFF_BUTTONS = 4
OS_MOUSE_BYTES = 6
OS_KEY_SHIFT = 0x626         # u16: the shift-key mask vq_key_s reports
OS_VDI_STATE = 0x628         # the VDI workstation attributes (field offsets in harness.py)
OS_VDI_STATE_BYTES = 28
# The keystrokes queued BEHIND OS_CON_CHAR: `harness.console_keys` stages a walk of them and every
# console read takes one. Up at the top of the block rather than beside OS_CON_CHAR because there is
# no room there — OS_RANDOM_VALUE and the PSG file already follow it. See include/os.h.
OS_CON_QUEUE = 0x644         # u32 x (OS_CON_QUEUE_MAX - 1)
OS_CON_QUEUE_MAX = 8         # keystrokes one case may stage: OS_CON_CHAR plus this many followers
OS_CON_QUEUE_BYTES = (OS_CON_QUEUE_MAX - 1) * 4
OS_POKE_BLOCK_END = OS_CON_QUEUE + OS_CON_QUEUE_BYTES   # first address above the poked block (0x660)

# ---- the off-image OS event ledger's kinds (mirror of include/os.h, "Phase 13") ----
# Here rather than in harness.py for this module's SECOND reason: `test/test_os_model.py` runs in a
# bare checkout and cannot import harness, so it spelt them as literals and a value changed in os.h
# alone would have left every IKBD command comparing as a console byte. harness.py re-exports them.
OS_EVENT_NONE = 0            # the out-parameter's "this call had no off-image effect"
OS_EVENT_CONOUT = 1          # value = a character byte written to the console
OS_EVENT_IKBD = 2            # value = a command byte sent to the IKBD (BIOS Bconout, device 4)
OS_EVENT_GEM_MOUSE = 3       # value = AES graf_mouse's mode word
OS_EVENT_VDI_CURSOR = 4      # value = 1 for VDI v_show_c, 0 for v_hide_c
OS_EVENT_AUXOUT = 5          # value = a character byte written to AUX: (GEMDOS Cauxout)
OS_EVENT_PRNOUT = 6          # value = a character byte written to the printer (GEMDOS Cprnout)
OS_EVENT_PTERM = 7           # value = the exit code the process ended with (GEMDOS Pterm)
OS_EVENT_SETSCREEN = 8       # value = the LOGICAL base XBIOS Setscreen was given
OS_EVENT_SETPALETTE = 9      # value = the address of the sixteen-word colour table
OS_EVENT_SETCOLOR = 10       # value = index << 16 | the colour word (XBIOS Setcolor)
OS_EVENT_VSYNC = 11          # value = 0: XBIOS Vsync takes no argument and answers nothing

# ---- the staged-file window's DEFAULT place (mirror of include/os.h) ----
# Here rather than with the rest of the file-staging map in ``harness.py`` for this module's first
# reason: the table's address is the ceiling the Malloc arena may not reach, and BOTH files ask about
# it — ``harness._vet_os_memory_map`` checks where the arena is PLACED and
# ``emu._vet_heap_within_bounds`` checks how far one run grew it.
#
# The DEFAULT, because the window is one of the two regions a project may place (project.toml's
# ``fs_base``; see ../README.md, "The staged-file window is the second region a project places").
# ``emu.OS_FS_TABLE`` / ``emu.OS_FS_STAGING`` are the resolved addresses every guard reads, and
# ``harness`` serves those back under its own names — so the rest of the map still reads as one
# namespace, and no copy of a live value can go stale.
OS_FS_TABLE_DEFAULT = 0xBF000
# ...and the DISTANCE from the table to the raw file bytes. A distance and not a second address, so
# a project that moves the window moves both halves together and the table can never be placed over
# its own staging area (os.h asserts OS_FS_SLOTS * OS_FS_ENTRY fits inside it at compile time).
OS_FS_STAGING_OFFSET = 0x1000

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


# The model's own fields inside the block, by name — what a declaration is measured against. A
# span covering more than one of them is a whole-block waiver wearing a range's clothes.
POKED_INPUT_FIELDS = (("OS_CON_PENDING", OS_CON_PENDING, 4),
                      ("OS_CON_CHAR", OS_CON_CHAR, 4),
                      ("OS_RANDOM_VALUE", OS_RANDOM_VALUE, 4),
                      ("OS_PSG_REGS", OS_PSG_REGS, OS_PSG_NREGS),
                      ("OS_MOUSE", OS_MOUSE, OS_MOUSE_BYTES),
                      ("OS_KEY_SHIFT", OS_KEY_SHIFT, 2),
                      ("OS_VDI_STATE", OS_VDI_STATE, OS_VDI_STATE_BYTES),
                      ("OS_CON_QUEUE", OS_CON_QUEUE, OS_CON_QUEUE_BYTES))


def poked_input_fields_touched(addr, length):
    """The names of the model's fields a poke of ``length`` bytes at ``addr`` reaches into.

    Used two ways and both are about making a mistake loud rather than convenient: ``project.load``
    refuses a DECLARATION spanning more than one field, and ``harness.make_image`` notes when a
    SERVED poke lands on one, so a hand-staged console key cannot quietly become a game-data seed.
    """
    return tuple(name for name, at, size in POKED_INPUT_FIELDS
                 if addr < at + size and at < addr + length)


def poke_is_declared_program_data(addr, length, declared):
    """Is this whole poke inside a range the PROJECT declared to be its own program's data?

    ``poke_hits_poked_input`` above answers "does this touch the block", which is all the kit can
    know by itself: under the overlap those addresses ARE the game's bytes, and nothing in the kit
    can tell a poke staging OS model state from one seeding a game variable that happens to share an
    address. The project can, and this is how it says so — ``project.toml``'s
    ``poked_input_program_data``, a list of ``[address, length]`` the game's own code reads and
    writes at that address.

    THE DECLARATION DOES NOT RE-OPEN THE HAZARD IT LOOKS LIKE. What makes an overlapping poke
    dangerous is a TRAP serving it back — the model reading the game's code as a keystroke, or
    clearing four bytes of it — and that is refused per run, on every run, by
    ``emu._vet_no_poked_input_read``, declaration or no declaration. What this permits is only the
    seeding of a byte the game itself owns.

    WHOLLY inside, never partly: a poke that straddles the boundary is half game data and half model
    state, and serving it would write the model's half from a value the project never declared.

    ``declared`` is a sequence of ``(lo, hi)`` half-open ranges (``project.load`` builds it); an
    empty one — every project but the declaring ones — answers False after one `not`.
    """
    if not declared or length <= 0:
        return False
    return any(lo <= addr and addr + length <= hi for lo, hi in declared)


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
