"""What BIOS Bconstat, Bconin, Bconout and Bcostat share: one frame, one walk, one no-driver answer.

The four entries are the same four instructions over four different tables in RAM
(`src/bios/bcon.c`), so their batteries would otherwise keep four copies of how to enter them, how
to read a table out of the snapshot, and what a device with no driver comes back as. Each battery
keeps only what IS its own: which drivers its own table reaches, and what those drivers answer.
"""
import ctypes

import case
from harness import BASE_IMAGE, _lib, addrs

# The three STATUS/INPUT cores are one signature — (image, the D0 the trap dispatcher left, the
# device word), and the whole of D0 back — so it is declared once rather than three times over.
for _core in (_lib.bios_bconstat, _lib.bios_bconin, _lib.bios_bcostat):
    _core.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32, ctypes.c_uint16]
    _core.restype = ctypes.c_uint32

# ...and `Bconout`, which is that signature plus the CHARACTER WORD the ROM reads at 6(sp).
_lib.bios_bconout.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_uint32,
                              ctypes.c_uint16, ctypes.c_uint16]
_lib.bios_bconout.restype = ctypes.c_uint32

# A caller's D0 with a marked high half. The no-driver arm returns it with only its LOW word replaced
# (`no_driver_result`), so a reconstruction that cleared or rebuilt the high half passes every other
# case in the three files and fails this one.
MARKED_D0 = 0xBEEF_0000


def runner(entry, core):
    """The `run(device, ...)` one of the three batteries uses.

    `entry` is the ROM address and `core` the candidate function. `entry_d0` defaults to `entry`
    itself, because that is what the trap dispatcher really leaves in D0: the routine's own address,
    which it loaded in order to jump through it.
    """
    def run(device, pokes=None, entry_d0=None, poison=True, **seeds):
        """`seeds` are `case.run`'s own — `io_seed` above all, which is how a case declares the
        hardware byte a driver reads. Forwarded rather than enumerated, for `case.run`'s reason: they
        are the kit's list and naming them here would be a second copy to keep level with it."""
        d0 = entry if entry_d0 is None else entry_d0

        def glue(_harness_lib, buf):
            # `core` is the same bound ctypes function the harness would hand back through its own
            # argument, already carrying the signature declared above.
            return core(buf, d0, device & 0xFFFF)

        return case.run(entry,
                        {"a5": 0, "d0": d0, "_pokes": {**case.word_arg(device), **(pokes or {})}},
                        glue, poison=poison, **seeds)
    return run


def output_runner(entry, core):
    """...and `Bconout`'s, which is the same walk with a CHARACTER WORD above the device word.

    A separate constructor rather than a flag on the one above, because the extra argument changes
    both halves at once — the frame the case pokes and the C signature the glue calls — and a runner
    that took an optional character would leave every other battery's frame one word longer than the
    routine it proves reads.
    """
    def run(device, character, pokes=None, entry_d0=None, poison=True, **seeds):
        d0 = entry if entry_d0 is None else entry_d0

        def glue(_harness_lib, buf):
            return core(buf, d0, device & 0xFFFF, character & 0xFFFF)

        return case.run(entry,
                        {"a5": 0, "d0": d0,
                         "_pokes": {**case.word_args(device, character), **(pokes or {})}},
                        glue, poison=poison, **seeds)
    return run


def table_entries(table):
    """One BIOS character-device vector table, as the SNAPSHOT holds it.

    WHICH driver a device number reaches is a fact about RAM rather than about the ROM — the boot
    copies the tables from $fc09ae and anything may replace an entry afterwards — so every battery
    reads its table out of the capture instead of assuming it.
    """
    entries = addrs.XCON_TABLE_DEVICES * addrs.XCON_TABLE_ENTRY_BYTES
    return [int.from_bytes(bytes(BASE_IMAGE[at:at + addrs.XCON_TABLE_ENTRY_BYTES]), "big")
            for at in range(table, table + entries, addrs.XCON_TABLE_ENTRY_BYTES)]


def no_driver_result(entry_d0, device):
    """What a device whose table entry is the shared `rts` at $fc0670 answers.

    Nothing runs at all: the dispatch's own `move.w 4(sp),d0` and `lsl.w #2,d0` have replaced D0's
    LOW WORD with the table offset and left the caller's high half alone, and the `rts` hands that
    back. Garbage, but deterministic garbage — and a reconstruction that answered 0 for "no driver"
    would be wrong in a way no user of Bconstat would ever notice.
    """
    return (entry_d0 & 0xFFFF_0000) | ((device * addrs.XCON_TABLE_ENTRY_BYTES) & 0xFFFF)


def assert_no_driver(run, device):
    """...asserted through a marked D0, which is the only way to see that the high half survives."""
    assert run(device, entry_d0=MARKED_D0)["regs"]["d0"] == no_driver_result(MARKED_D0, device)
