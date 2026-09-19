"""The VERTICAL BLANK handler @ $fc06de — vector $70, fifty times a second, and the instruction the
boot snapshot itself is captured at (`tools/boot_snapshot.py`).

Everything the handler reads is RAM the case can perturb, and everything it does that is NOT memory
is off-image: the shifter's resolution byte and the MFP's monitor bit are DECLARED reads (`io_seed`),
the palette row, the two screen-base bytes and the resolution store are ledger entries (`hw.h`), and
what it CALLS — `swv_vec`, `_vblqueue`'s slots and `scr_dump` — are staged routines. So the green on
a case here means the image agreed, the ordered I/O read stream agreed, the ordered hardware write
stream agreed, and the routines that ran were the ones the vectors named.

TWO THINGS EVERY CASE HERE STAGES, and both are the machine rather than the routine:

* `flock` is set. The `bsr $fc1bc4` into the floppy's own VBL service is unconditional, and its body
  past that gate polls the FDC status register — the one shape no declaration can describe (`vbl.c`,
  "WHAT IS NOT RECONSTRUCTED"). With a disk operation in flight it stores one byte and returns,
  which is a real arm of a real machine and the one this wave reconstructs.
* `_vblqueue` points at a staged array instead of the system's own at $4ce. The captured machine has
  a ROM routine in slot 0 ($fcff2a, the Line-A mouse's frame work), which is a reconstruction of its
  own; pointing the system variable somewhere else is the same kind of input as staging a driver.
"""
import ctypes
import struct

import pytest

import case
import isr
from harness import _lib, addrs, emu

_lib.isr_vbl.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
_lib.isr_vbl.restype = None

# ---- this battery's corner of the staging band ---------------------------------------------------
SWV_STUB = isr.STUB_BAND + 0x00
DUMP_STUB = isr.STUB_BAND + 0x10
DECOY_STUB = isr.STUB_BAND + 0x20
QUEUE = isr.STUB_BAND + 0x40                  # eight longwords: the staged `_vblqueue`
QUEUE_SLOTS = 8
# 16 bytes apart, which is more than the longest stub here (`store_byte` is 8 and `store_word` 8,
# plus the two of the `rts`): a stride that only just fits lets one stub's last instruction be
# overwritten by the next one's first, and the oracle then falls THROUGH into it — which reads as a
# routine the walk called and did not.
QUEUE_STUB_STRIDE = 0x10
QUEUE_STUBS = tuple(isr.STUB_BAND + 0x60 + QUEUE_STUB_STRIDE * slot for slot in range(4))
MARKS = isr.MARKS                             # one byte per staged routine, so an order is readable
PALETTE_SOURCE = isr.STUB_BAND + 0x180        # sixteen colour words
CURSOR_CELL = isr.STUB_BAND + 0x1C0           # ...and the bytes the cursor inversion walks
CURSOR_CELL_BYTES = 0x40
assert CURSOR_CELL + CURSOR_CELL_BYTES <= isr.ISR_BAND + isr.ISR_BAND_BYTES

MARK = isr.MARK

# What a case declares the machine held. Bit 7 of the GPIP is HIGH when a COLOUR monitor is plugged
# in, so these two are the pair that agree — the follower does nothing and the rest of the handler
# runs. Every case says which it means rather than inheriting a default nobody reads.
COLOUR_MONITOR = 1 << addrs.MFP_GPIP_MONOCHROME_BIT
MONO_MONITOR = 0
# ...and a mono monitor with every OTHER bit of the register set, which is the byte that separates
# `btst #7` from a test of the whole register: a reconstruction reading "$fffa01 is zero" agrees with
# `MONO_MONITOR` and calls this one a colour monitor.
MONO_MONITOR_NOISY = 0xFF & ~(1 << addrs.MFP_GPIP_MONOCHROME_BIT)
MONO_MONITORS = (MONO_MONITOR, MONO_MONITOR_NOISY)
ST_LOW, ST_MEDIUM, ST_HIGH = 0, 1, 2


marker_routine = isr.marker_routine


def quiet_pokes(overrides=None):
    """The state a frame with nothing queued has: the floppy gate shut, an empty staged queue.

    `overrides` is a dict rather than keyword arguments because every key here is an ADDRESS.
    """
    return {addrs.SYSVAR_FLOCK: struct.pack(">H", 1),
            addrs.SYSVAR_VBLQUEUE: struct.pack(">I", QUEUE),
            addrs.SYSVAR_NVBLS: struct.pack(">H", 0),
            QUEUE: bytes(QUEUE_SLOTS * addrs.VBLQUEUE_ENTRY_BYTES),
            **(overrides or {})}


def _glue(lib, buf):
    lib.isr_vbl(buf)


def run(pokes=None, *, resolution=ST_LOW, gpip=COLOUR_MONITOR, routines=None, poison=True,
        regs=None, max_insns=isr.DEFAULT_MAX_INSNS):
    """One differential of the VBL over a declared machine and a staged set of routines."""
    return isr.run(addrs.ISR_VBL, _glue, pokes=pokes if pokes is not None else quiet_pokes(),
                   routines=routines, poison=poison, regs=regs, max_insns=max_insns,
                   io_seed={addrs.SHIFTER_RESOLUTION: resolution, addrs.MFP_GPIP: gpip})


long_in_snapshot, word_in_snapshot = isr.long_in_snapshot, isr.word_in_snapshot


# ---- what the case shape rests on ------------------------------------------------------------------

def test_the_vector_table_still_points_at_this_handler():
    assert isr.vector_in_snapshot(addrs.VECTOR_VBL) == addrs.ISR_VBL


def test_the_mfp_gpip_this_project_names_is_the_kit_s_own_slot():
    """`addrs.h` spells $fffa01 because `tools/addrs.py` reads integer defines only, and the kit's
    `os.h` spells it as `OS_HW_MFP_GPIP`. One of the two has to be the copy, so it is pinned rather
    than trusted: a slot renumbered or an address corrected on one side reddens here."""
    assert addrs.MFP_GPIP in emu.HW_ADDRS


def test_the_snapshot_s_console_block_is_the_geometry_this_reconstructs():
    """The cursor cases below stage their own geometry so the inversion fits in the staging band.
    This is what says the staged numbers stand for something: the captured machine's own block is a
    low-resolution 4-plane screen with an 8-line cell on a 160-byte pitch, and the cursor sits at the
    top-left of the screen `_v_bas_ad` names."""
    assert word_in_snapshot(addrs.CON_PLANES) == 4
    assert word_in_snapshot(addrs.CON_CELL_HEIGHT) == 8
    assert word_in_snapshot(addrs.CON_LINE_BYTES) == 160
    assert long_in_snapshot(addrs.CON_CURSOR_ADDRESS) == long_in_snapshot(addrs.SYSVAR_V_BAS_AD)


# ---- the two clocks and the semaphore ---------------------------------------------------------------

def test_a_quiet_frame_counts_both_clocks_and_touches_nothing_else():
    """The whole of a frame with nothing queued: two counters, the semaphore down and back, and the
    one byte the floppy service sets before its gate. A reconstruction that did anything more shows
    up as an extra address in the write set rather than as a value somewhere."""
    info = run()
    assert case.written(info, addrs.SYSVAR_FRCLOCK, 4) == long_in_snapshot(addrs.SYSVAR_FRCLOCK) + 1
    assert case.written(info, addrs.SYSVAR_VBCLOCK, 4) == long_in_snapshot(addrs.SYSVAR_VBCLOCK) + 1
    assert case.written(info, addrs.SYSVAR_VBLSEM, 2) == word_in_snapshot(addrs.SYSVAR_VBLSEM)
    assert info["writes"][addrs.FLOPPY_VBL_ENTERED] == 0xFF
    touched = {address for address in info["writes"] if address < emu.STACK_GUARD_LO}
    expected = ({addrs.SYSVAR_FRCLOCK + i for i in range(4)}
                | {addrs.SYSVAR_VBCLOCK + i for i in range(4)}
                | {addrs.SYSVAR_VBLSEM + i for i in range(2)}
                | {addrs.FLOPPY_VBL_ENTERED})
    assert touched == expected, f"the handler wrote {sorted(hex(a) for a in touched - expected)}"


# The semaphore values that separate the two paths, at the boundary the `bmi` really tests: 1 is the
# only open state the machine ever has, 0 and below are taken, and $8000 is the value whose
# decrement is POSITIVE — a reconstruction testing `<= 0` rather than the sign bit runs the body
# there where the ROM does not, and one testing the sign of the value BEFORE the decrement gets 1
# and 0 the wrong way round.
SEMAPHORES = (1, 2, 0x7FFF, 0, 0xFFFF, 0x8000, 0x8001)


@pytest.mark.parametrize("semaphore", SEMAPHORES)
def test_the_frame_clock_counts_blanks_and_the_vbl_clock_counts_those_it_serviced(semaphore):
    """`_frclock` is bumped before the semaphore is even looked at; `_vbclock` only on the path that
    does the work. That ordering is the whole difference between the two, and the taken-semaphore
    arm is what makes it visible."""
    info = run(quiet_pokes({addrs.SYSVAR_VBLSEM: struct.pack(">H", semaphore)}))
    serviced = ((semaphore - 1) & 0xFFFF) < 0x8000

    assert case.written(info, addrs.SYSVAR_FRCLOCK, 4) == long_in_snapshot(addrs.SYSVAR_FRCLOCK) + 1
    assert case.written(info, addrs.SYSVAR_VBLSEM, 2) == semaphore
    assert (addrs.SYSVAR_VBCLOCK in info["writes"]) == serviced
    assert (addrs.FLOPPY_VBL_ENTERED in info["writes"]) == serviced


def test_the_semaphore_is_read_back_before_it_is_released():
    """`addq.w #1,vblsem` reads the word again rather than adding one to what the entry computed, so
    a queue routine that stores a semaphore of its own has its value incremented — not the entry's.
    A reconstruction that kept the decremented value in a register passes every other case here."""
    taken_by_someone_else = 0x0040
    routine = (isr.store_word(taken_by_someone_else, addrs.SYSVAR_VBLSEM) + isr.RTS,
               lambda buf, _argument: isr.poke(buf, addrs.SYSVAR_VBLSEM,
                                               struct.pack(">H", taken_by_someone_else)))
    pokes = quiet_pokes({addrs.SYSVAR_NVBLS: struct.pack(">H", 1),
                           QUEUE: struct.pack(">I", QUEUE_STUBS[0])})
    info = run(pokes, routines={QUEUE_STUBS[0]: routine}, poison=False)
    assert case.written(info, addrs.SYSVAR_VBLSEM, 2) == taken_by_someone_else + 1


# ---- the monitor follower -----------------------------------------------------------------------

@pytest.mark.parametrize("resolution", (ST_LOW, ST_MEDIUM, 0xFC, 0xFD))
def test_a_colour_monitor_on_a_colour_resolution_changes_nothing(resolution):
    """`and.b #3` first, so the six bits above the mode are not part of the test — $fc reads as
    low resolution and $fd as medium."""
    info = run(resolution=resolution, gpip=COLOUR_MONITOR)
    assert addrs.SYSVAR_SSHIFTMD not in info["writes"]
    assert info["regs"]["hw_writes"] == []


@pytest.mark.parametrize("gpip", MONO_MONITORS)
@pytest.mark.parametrize("resolution", (ST_HIGH, 3, 0xFE, 0xFF))
def test_a_mono_monitor_on_a_mono_resolution_changes_nothing(resolution, gpip):
    info = run(resolution=resolution, gpip=gpip)
    assert addrs.SYSVAR_SSHIFTMD not in info["writes"]
    assert info["regs"]["hw_writes"] == []


@pytest.mark.parametrize("gpip", MONO_MONITORS)
def test_a_mono_monitor_arriving_forces_st_high(gpip):
    """The colour-to-mono direction takes no notice of `defshiftmd` at all: the machine has one
    monochrome mode and the handler writes it, shadows it and tells the VDI.

    ONE RESOLUTION, because this arm reads the register only to choose itself and the four-value
    case above already separates `< 2` from `== 0`; what is parametrized here is the GPIP byte,
    which is the input this arm is about. The arm also spends 2001 passes of a `dbf` letting the
    shifter settle, so a value that carries no claim of its own is 2000 oracle instructions.
    """
    routines = {SWV_STUB: marker_routine(0)}
    info = run(quiet_pokes({addrs.SYSVAR_SWV_VEC: struct.pack(">I", SWV_STUB)}),
               resolution=ST_LOW, gpip=gpip, routines=routines)
    assert info["writes"][addrs.SYSVAR_SSHIFTMD] == ST_HIGH
    assert info["regs"]["hw_writes"] == [(addrs.SHIFTER_RESOLUTION, 1, ST_HIGH)]
    assert info["writes"][MARKS] == MARK, "swv_vec was not called on a resolution change"


# What the colour-monitor-returns arm does with each `defshiftmd` it can find. `cmp.b #2 / blt` is a
# SIGNED byte test, so $80 and $ff are BELOW 2 and are kept exactly as they stand — which is the
# pair that separates the ROM's test from the `< 2` an unsigned reading would write.
@pytest.mark.parametrize("default_mode,written", ((0, 0), (1, 1), (2, 0), (3, 0), (0x7F, 0),
                                                  (0x80, 0x80), (0xFE, 0xFE), (0xFF, 0xFF)))
def test_a_colour_monitor_arriving_restores_the_default_mode(default_mode, written):
    routines = {SWV_STUB: marker_routine(0)}
    info = run(quiet_pokes({addrs.SYSVAR_SWV_VEC: struct.pack(">I", SWV_STUB),
                              addrs.SYSVAR_DEFSHIFTMD: bytes([default_mode])}),
               resolution=ST_HIGH, gpip=COLOUR_MONITOR, routines=routines)
    assert info["writes"][addrs.SYSVAR_SSHIFTMD] == written
    assert info["regs"]["hw_writes"] == [(addrs.SHIFTER_RESOLUTION, 1, written)]
    assert info["writes"][MARKS] == MARK


def test_the_resolution_change_calls_the_routine_swv_vec_names_and_not_another():
    """A DECOY staged beside the named routine, which is what makes the vector an input on both
    sides: the candidate reaches its routine through an address-keyed hook, so one with a baked-in
    address marks the decoy's byte instead of this one's."""
    routines = {SWV_STUB: marker_routine(0), DECOY_STUB: marker_routine(1)}
    info = run(quiet_pokes({addrs.SYSVAR_SWV_VEC: struct.pack(">I", SWV_STUB)}),
               resolution=ST_LOW, gpip=MONO_MONITOR, routines=routines)
    assert info["writes"][MARKS] == MARK
    assert MARKS + 1 not in info["writes"], "the decoy ran"


# ---- the palette -----------------------------------------------------------------------------------

def test_a_frame_with_no_palette_queued_writes_no_colour():
    assert run()["regs"]["hw_writes"] == []


PALETTE = tuple(0x0123 + 0x0111 * entry for entry in range(addrs.SHIFTER_PALETTE_ENTRIES))


def test_a_queued_palette_is_moved_word_by_word_and_the_pointer_is_cleared():
    """Sixteen WORD stores into the shifter's colour row, in order, and then `colorptr` is zeroed so
    the next frame does nothing. The row is off-image, so the ordered write ledger is the whole
    comparison — a reconstruction that stored bytes, or the wrong count, or the words backwards, is
    separable from a correct one by nothing else."""
    info = run(quiet_pokes({addrs.SYSVAR_COLORPTR: struct.pack(">I", PALETTE_SOURCE),
                              PALETTE_SOURCE: struct.pack(">16H", *PALETTE)}))
    assert info["regs"]["hw_writes"] == [
        (addrs.SHIFTER_PALETTE + entry * addrs.PALETTE_ENTRY_BYTES, 2, colour)
        for entry, colour in enumerate(PALETTE)]
    assert case.written(info, addrs.SYSVAR_COLORPTR, 4) == 0


def test_the_palette_is_read_from_wherever_colorptr_points():
    """...and from there rather than from the block the snapshot happens to hold: the same sixteen
    words staged at a second address come out of the ledger unchanged."""
    elsewhere = PALETTE_SOURCE + 0x20
    info = run(quiet_pokes({addrs.SYSVAR_COLORPTR: struct.pack(">I", elsewhere),
                              elsewhere: struct.pack(">16H", *reversed(PALETTE))}))
    assert [value for _at, _width, value in info["regs"]["hw_writes"]] == list(reversed(PALETTE))


# ---- the screen base -------------------------------------------------------------------------------

def test_a_frame_with_no_screen_queued_leaves_the_base_alone():
    info = run()
    assert addrs.SYSVAR_V_BAS_AD not in info["writes"]


# Bases whose two programmed bytes differ, plus the values that separate the ROM's `lsr.l #8` /
# `lsr.w #8` pair from a reconstruction that shifted the longword twice or took the wrong halves.
SCREEN_BASES = (0x00F8_0000, 0x0001_0000, 0x0000_FF00, 0x00FF_FF00, 0x1234_5678, 0xFFFF_FFFF)


@pytest.mark.parametrize("base", SCREEN_BASES)
def test_a_queued_screen_base_reaches_v_bas_ad_and_the_shifter(base):
    """MID first, then HIGH — the ROM's own order, and the ledger compares it. The low byte of the
    address is not programmed at all: an ST screen has no register for it."""
    info = run(quiet_pokes({addrs.SYSVAR_SCREENPT: struct.pack(">I", base)}))
    assert case.written(info, addrs.SYSVAR_V_BAS_AD, 4) == base
    assert info["regs"]["hw_writes"] == [
        (addrs.SHIFTER_BASE_MID, 1, (base >> addrs.SHIFTER_BASE_SHIFT) & 0xFF),
        (addrs.SHIFTER_BASE_HIGH, 1, (base >> (2 * addrs.SHIFTER_BASE_SHIFT)) & 0xFF)]


def test_screenpt_is_not_cleared_the_way_colorptr_is():
    """THE ROM'S OWN ASYMMETRY, pinned so it cannot read as an omission here. `colorptr` is zeroed
    after the palette moves and `screenpt` is not, so the same base is re-programmed on every frame
    until something stores a new one — which is why `Setscreen` is what clears it and the handler
    never does."""
    base = 0x00F8_0000
    info = run(quiet_pokes({addrs.SYSVAR_SCREENPT: struct.pack(">I", base)}))
    assert addrs.SYSVAR_SCREENPT not in info["writes"]


# ---- the cursor blink ------------------------------------------------------------------------------
# The console block, staged: a 2-plane 4-line cell on an 8-byte pitch, which fits in the staging band
# where the machine's own 160-byte pitch would not. The geometry is RAM, so these are inputs.
CELL_PLANES, CELL_HEIGHT, CELL_PITCH = 2, 4, 8
CURSOR_PATTERN = bytes(range(CURSOR_CELL_BYTES))
BLINKS = 1 << addrs.CON_FLAG_BLINKS
DRAWN = 1 << addrs.CON_FLAG_DRAWN


def cursor_pokes(flags, timer, rate=0x1E, disable=0, cursor=CURSOR_CELL, overrides=None):
    return quiet_pokes({addrs.CON_CURSOR_DISABLE: struct.pack(">H", disable),
                          addrs.CON_BLINK_TIMER: bytes([timer]),
                          addrs.CON_BLINK_RATE: bytes([rate]),
                          addrs.CON_STATE_FLAGS: bytes([flags]),
                          addrs.CON_CURSOR_ADDRESS: struct.pack(">I", cursor),
                          addrs.CON_PLANES: struct.pack(">H", CELL_PLANES),
                          addrs.CON_CELL_HEIGHT: struct.pack(">H", CELL_HEIGHT),
                          addrs.CON_LINE_BYTES: struct.pack(">H", CELL_PITCH),
                          CURSOR_CELL: CURSOR_PATTERN,
                        **(overrides or {})})


def inverted_cells(cursor=CURSOR_CELL, planes=CELL_PLANES, height=CELL_HEIGHT, pitch=CELL_PITCH):
    """Where the inversion lands: one byte per scan line of each plane, the planes one word apart."""
    return {cursor + plane * addrs.SCREEN_PLANE_WORD_BYTES + row * pitch
            for plane in range(planes) for row in range(height)}


def cell_writes(info):
    """...and which of the staged cell's bytes the run actually touched."""
    return {at for at in info["writes"] if CURSOR_CELL <= at < CURSOR_CELL + CURSOR_CELL_BYTES}


@pytest.mark.parametrize("disable", (1, 2, 0xFFFF, 0x8000))
def test_a_suppressed_cursor_does_not_even_count_down(disable):
    """The first gate is a WORD test, and it is before the timer: a machine with the cursor
    suppressed does not blink and does not get closer to blinking either."""
    info = run(cursor_pokes(BLINKS, timer=1, disable=disable))
    assert addrs.CON_BLINK_TIMER not in info["writes"]


@pytest.mark.parametrize("timer", (2, 3, 0x1E, 0xFF))
def test_a_cursor_whose_timer_has_not_run_out_only_counts_down(timer):
    info = run(cursor_pokes(BLINKS, timer=timer))
    assert info["writes"][addrs.CON_BLINK_TIMER] == timer - 1
    assert addrs.CON_STATE_FLAGS not in info["writes"]


def test_a_timer_of_zero_wraps_through_the_whole_byte():
    """`subq.b #1` on a zero byte is $ff, not -1 and not a toggle: the blink is 255 frames away, not
    this frame. A reconstruction that tested `<= 0` toggles here."""
    info = run(cursor_pokes(BLINKS, timer=0))
    assert info["writes"][addrs.CON_BLINK_TIMER] == 0xFF
    assert addrs.CON_STATE_FLAGS not in info["writes"]


@pytest.mark.parametrize("rate", (1, 2, 0x1E, 0xFF, 0))
def test_a_blinking_cursor_reloads_the_rate_toggles_and_inverts_its_cell(rate):
    """The timer is reloaded from `CON_BLINK_RATE` — the byte `Cursconf` 4 sets — and the DRAWN bit
    is a `bchg`, so the same case run twice puts the cell back."""
    info = run(cursor_pokes(BLINKS, timer=1, rate=rate))
    assert info["writes"][addrs.CON_BLINK_TIMER] == rate
    assert info["writes"][addrs.CON_STATE_FLAGS] == (BLINKS ^ DRAWN)
    assert cell_writes(info) == inverted_cells()


def test_the_toggle_goes_both_ways():
    info = run(cursor_pokes(BLINKS | DRAWN, timer=1))
    assert info["writes"][addrs.CON_STATE_FLAGS] == BLINKS


def test_a_steady_cursor_that_is_already_drawn_is_stored_back_and_left_on_screen():
    """`bset #1,(a4)` is a read-modify-write: the flags byte is written even when the bit was
    already set, and only the `beq` that follows decides whether the CELL is touched.

    WHAT IS PROVED HERE IS THE CELL, and the store is the ORACLE's claim alone — the one place in
    this wave where a transcribed instruction has no surface at all. A `bset` over a bit that is
    already set writes the byte that is already there, so the image diff cannot see it, and no other
    instrument can: it costs the same cycles either way and reaches no chip.

    THE ATTRIBUTION PASS IS NOT WHAT CARRIES THE OTHER TWO STORES EITHER, which is worth saying here
    because this case is where a reader looks for the difference. Poisoning inverts `vblsem` along
    with everything else the oracle wrote, so almost every poisoned pass in this battery re-enters
    with a closed semaphore and never reaches the cursor at all. What holds `subq.b` and `bchg` is
    the PLAIN diff: both always change the byte they store. `src/bios/vbl.c` says the same at the
    site.
    """
    info = run(cursor_pokes(DRAWN, timer=1))
    assert info["writes"][addrs.CON_STATE_FLAGS] == DRAWN
    assert not cell_writes(info)


def test_a_steady_cursor_that_is_not_drawn_is_drawn_once():
    info = run(cursor_pokes(0, timer=1))
    assert info["writes"][addrs.CON_STATE_FLAGS] == DRAWN
    assert cell_writes(info) == inverted_cells()


def test_the_cell_is_inverted_where_the_cursor_address_points():
    """...and not at a base the reconstruction remembers: the same cell staged half a cell along."""
    elsewhere = CURSOR_CELL + 1
    info = run(cursor_pokes(BLINKS, timer=1, cursor=elsewhere))
    assert cell_writes(info) == inverted_cells(elsewhere)


# Geometries whose two `dbf` counts differ, so a reconstruction that swapped them, or that used one
# where the other belongs, diverges. The pitch is what tells the row step from the plane step.
GEOMETRIES = ((1, 1, 1), (1, 4, 2), (4, 1, 3), (2, 4, 8), (3, 5, 4), (8, 2, 16))


@pytest.mark.parametrize("planes,height,pitch", GEOMETRIES)
def test_the_inversion_walks_the_geometry_the_console_block_declares(planes, height, pitch):
    info = run(cursor_pokes(BLINKS, timer=1,
                            overrides={addrs.CON_PLANES: struct.pack(">H", planes),
                                       addrs.CON_CELL_HEIGHT: struct.pack(">H", height),
                                       addrs.CON_LINE_BYTES: struct.pack(">H", pitch)}))
    assert cell_writes(info) == inverted_cells(planes=planes, height=height, pitch=pitch)


# A `dbf` count of ZERO is a full 65,536 passes, not none — the loop tests the register AFTER
# decrementing it, so 0 goes to -1 through every value in between (`m68k_idioms.h`'s `loop_passes`).
# The case that exercises it has to make those passes land on ONE byte, or it would walk 64 KB
# across the staging band and out the other side: a pitch of 0 leaves the row step at nothing, so
# the cell's first byte is inverted 65,536 times and comes back to the value it started at.
#
# WHAT IT PINS, AND WHAT IT CANNOT. It runs the arm on both sides, so a reconstruction that walks
# off the cell, that faults, or that makes an ODD number of passes (65,535, say) is refused by the
# image diff. The pass COUNT ITSELF IS NOT PINNED HERE and cannot be by any case of this shape: a
# candidate that read the count as 0 and made NO pass leaves exactly the byte a candidate that made
# 65,536 does — an even number of inversions of one byte is the identity — and the host build has no
# write ledger for the differential to compare instead. Measured: the mutation `loop_passes(...)` ->
# the raw count survives this case. What would pin it is a Tier 3 row (200,000 instructions against
# our own), and that is a cost on `make test` for one branch the console driver never takes: the
# machine's own cell height is 8 (`test_the_snapshot_s_console_block_is_the_geometry_this
# _reconstructs`), and a zero would be a console block nothing in the ROM writes.
ZERO_COUNT_PASSES = 1 << 16
# ...and what those passes cost the ORACLE: three instructions each, which is past `isr.run`'s
# ordinary cap. Generous rather than tight — this is a guard against a runaway, not a measurement.
ZERO_COUNT_INSN_CAP = 4 * ZERO_COUNT_PASSES


def test_a_cell_height_of_zero_is_a_full_sixty_five_thousand_passes():
    info = run(cursor_pokes(BLINKS, timer=1,
                            overrides={addrs.CON_PLANES: struct.pack(">H", 1),
                                       addrs.CON_CELL_HEIGHT: struct.pack(">H", 0),
                                       addrs.CON_LINE_BYTES: struct.pack(">H", 0)}),
               max_insns=ZERO_COUNT_INSN_CAP)
    assert cell_writes(info) == {CURSOR_CELL}, "the walk did not stay on the one byte"
    assert info["writes"][CURSOR_CELL] == CURSOR_PATTERN[0], (
        f"{ZERO_COUNT_PASSES} inversions of one byte is an even number of them, so it ends where it "
        f"started; this run left {info['writes'][CURSOR_CELL]:#04x}")


# ---- the queue -------------------------------------------------------------------------------------

def test_a_queue_of_no_slots_calls_nothing():
    assert run(quiet_pokes({addrs.SYSVAR_NVBLS: struct.pack(">H", 0)}))["writes"].get(MARKS) \
        is None


def test_every_non_zero_slot_is_called_in_order_and_the_zeroes_are_skipped():
    """Four slots, two of them empty: `cmpa.l #0,a1 / beq` is the skip, and the ORDER is what the
    candidate's own call list is compared on."""
    slots = (QUEUE_STUBS[0], 0, QUEUE_STUBS[1], 0)
    routines = {QUEUE_STUBS[index]: marker_routine(index) for index in range(2)}
    info = run(quiet_pokes({addrs.SYSVAR_NVBLS: struct.pack(">H", len(slots)),
                              QUEUE: struct.pack(f">{len(slots)}I", *slots)}),
               routines=routines)
    assert info["writes"][MARKS] == MARK and info["writes"][MARKS + 1] == MARK
    assert isr.CALLS == [(QUEUE_STUBS[0], isr.NO_ARGUMENT), (QUEUE_STUBS[1], isr.NO_ARGUMENT)]


@pytest.mark.parametrize("slots", (1, 2, 3, 4))
def test_the_walk_is_exactly_nvbls_slots_long(slots):
    """`subq.w #1,d7 / dbf` — the count IS the number of slots, so the last one is reached and the
    one past it is not. Four routines staged and a shorter count is what separates them."""
    routines = {QUEUE_STUBS[index]: marker_routine(index) for index in range(4)}
    info = run(quiet_pokes({addrs.SYSVAR_NVBLS: struct.pack(">H", slots),
                              QUEUE: struct.pack(">4I", *QUEUE_STUBS)}),
               routines=routines)
    assert [index for index in range(4) if MARKS + index in info["writes"]] == list(range(slots))


def test_a_queue_routine_that_rewrites_the_queue_does_not_change_the_walk_it_is_in():
    """`movem.l d7/a0,-(sp)` around every call: the count and the cursor are the ones the walk
    started with, whatever the routine stores into `nvbls` or `_vblqueue`. A reconstruction that
    re-read either system variable per slot runs a different queue here."""
    def rewrite_the_queue(buf, _argument):
        isr.poke(buf, addrs.SYSVAR_NVBLS, b"\x00\x00")
        buf[MARKS] = MARK

    routines = {QUEUE_STUBS[0]: (isr.store_word(0, addrs.SYSVAR_NVBLS)
                                 + isr.store_byte(MARK, MARKS) + isr.RTS, rewrite_the_queue),
                QUEUE_STUBS[1]: marker_routine(1)}
    info = run(quiet_pokes({addrs.SYSVAR_NVBLS: struct.pack(">H", 2),
                              QUEUE: struct.pack(">2I", QUEUE_STUBS[0], QUEUE_STUBS[1])}),
               routines=routines, poison=False)
    assert info["writes"][MARKS + 1] == MARK, "the second slot was not reached"


# ---- the screen-dump hook ---------------------------------------------------------------------------

def test_a_frame_with_the_dump_flag_set_calls_nothing():
    assert word_in_snapshot(addrs.SYSVAR_DUMPFLG) != 0      # the captured machine's own state
    info = run()
    assert addrs.SYSVAR_DUMPFLG not in info["writes"]


def test_a_cleared_dump_flag_calls_scr_dump_and_sets_the_flag_again():
    """`tst.w _dumpflg / bne` — ZERO is the request, which is Alt-Help's doing; Scrdmp answers it and
    stores -1 so the next frame does not ask again."""
    info = run(quiet_pokes({addrs.SYSVAR_DUMPFLG: b"\x00\x00",
                              addrs.SYSVAR_SCR_DUMP: struct.pack(">I", DUMP_STUB)}),
               routines={DUMP_STUB: marker_routine(0)})
    assert info["writes"][MARKS] == MARK
    assert case.written(info, addrs.SYSVAR_DUMPFLG, 2) == 0xFFFF


def test_the_dump_calls_the_routine_scr_dump_names_and_not_another():
    info = run(quiet_pokes({addrs.SYSVAR_DUMPFLG: b"\x00\x00",
                              addrs.SYSVAR_SCR_DUMP: struct.pack(">I", DUMP_STUB)}),
               routines={DUMP_STUB: marker_routine(0), DECOY_STUB: marker_routine(1)})
    assert info["writes"][MARKS] == MARK and MARKS + 1 not in info["writes"]


# ---- what the handler gives back --------------------------------------------------------------------

def test_the_handler_gives_every_register_back():
    """`movem.l d0-a6,-(sp)` ... `movem.l (sp)+,d0-a6`, over the dirty file. The ORACLE's claim (see
    `isr.assert_registers_survived`) and the premise this whole battery rests on."""
    isr.assert_registers_survived(run())


def test_the_taken_semaphore_path_gives_them_back_too():
    """...and it never saved them: the early exit is four instructions and touches no register."""
    isr.assert_registers_survived(run(quiet_pokes({addrs.SYSVAR_VBLSEM: b"\x00\x00"})))


# ---- the cases this battery REGISTERS -----------------------------------------------------------
# Three, because the handler has three shapes and they cost very different numbers of cycles: the
# semaphore closed (four instructions), a frame with nothing queued, and a frame where everything
# the handler can be asked to do is asked of it at once.
IO_QUIET = {addrs.SHIFTER_RESOLUTION: ST_LOW, addrs.MFP_GPIP: COLOUR_MONITOR}

BUSY_FRAME = cursor_pokes(BLINKS, timer=1, overrides={
    addrs.SYSVAR_COLORPTR: struct.pack(">I", PALETTE_SOURCE),
    PALETTE_SOURCE: struct.pack(">16H", *PALETTE),
    addrs.SYSVAR_SCREENPT: struct.pack(">I", 0x00F8_0000),
    addrs.SYSVAR_NVBLS: struct.pack(">H", 2),
    QUEUE: struct.pack(">2I", QUEUE_STUBS[0], 0),
    addrs.SYSVAR_DUMPFLG: b"\x00\x00",
    addrs.SYSVAR_SCR_DUMP: struct.pack(">I", DUMP_STUB)})

REGISTERED = (
    # THE MONITOR CHANGE IS REGISTERED FOR ITS COST, not only for its behaviour: the arm spends 2001
    # passes of a `dbf` doing nothing, which is the shifter being given time to settle, and a Tier 1
    # differential cannot see a cycle. Delete the loop and every case above stays green; this row's
    # ratio is the whole of its surface (`vbl.c`, and `ipl.h` makes the same argument for its mask).
    {"name": "isr_vbl, a monitor change", "entry": addrs.ISR_VBL,
     "pokes": quiet_pokes({addrs.SYSVAR_SWV_VEC: struct.pack(">I", SWV_STUB)}),
     "routines": {SWV_STUB: marker_routine(0)},
     "io_seed": {addrs.SHIFTER_RESOLUTION: ST_LOW, addrs.MFP_GPIP: MONO_MONITOR}},
    {"name": "isr_vbl, the semaphore taken", "entry": addrs.ISR_VBL,
     "pokes": quiet_pokes({addrs.SYSVAR_VBLSEM: b"\x00\x00"}), "io_seed": IO_QUIET},
    {"name": "isr_vbl, a quiet frame", "entry": addrs.ISR_VBL,
     "pokes": quiet_pokes(), "io_seed": IO_QUIET},
    {"name": "isr_vbl, a frame with everything queued", "entry": addrs.ISR_VBL,
     "pokes": BUSY_FRAME, "io_seed": IO_QUIET,
     "routines": {QUEUE_STUBS[0]: marker_routine(0), DUMP_STUB: marker_routine(1)}},
)
VERIFIED_CASES = tuple(isr.registered(spec) for spec in REGISTERED)
# ...and the same four as WHOLE-HANDLER cases, which is the other relation: `src/bios/isr.S` — the
# stub a shipped ROM installs in vector $70, `_frclock` and the semaphore included — held to the
# image, the WHOLE register file and the chip that the ROM left (`isr.transcribed`). Every one of
# these frames is already in the band the diff drops, so they are the registered specs unchanged.
TRANSCRIBED = REGISTERED
TRANSCRIPTION_CASES = tuple(isr.transcribed(spec) for spec in TRANSCRIBED)


@pytest.mark.parametrize("spec", REGISTERED, ids=lambda spec: spec["name"])
def test_every_registered_case_is_one_this_battery_proves(spec):
    """The row and the differential are the SAME spec (`isr.registered` / `isr.run_spec`), so the
    registry describes runs that were verified rather than ones that were written down."""
    isr.run_spec(spec, _glue)


# WHAT THE SETTLE LOOP COSTS OUR OWN m68k BUILD, exactly, on the arm that runs it. `vbl.c` says the
# `dbf` has no surface but its cost, and `bench/tier3.py` pins the RATIO — but a ratio over 20,000
# cycles is far too coarse to hold a LOOP COUNT: a pass either way moves it by 0.0005, which is a
# quarter of the pin's own tolerance, so `SHIFTER_SETTLE_DBF_COUNT` could be edited by forty and
# nothing would redden. The absolute number is what holds it, and it is the RECREATE column because
# that is the side the count is in.
SETTLE_ROW = ("isr_vbl", "a monitor change")
# Re-pinned from 20,880 when `staged_call.h` began pinning A5 = 0 at every RAM-vector call (the
# base register `swv_vec` and every other system vector is entered with — see that header). The
# arm makes one such call, and what moved is the CODEGEN around the loop rather than the loop: six
# cycles, which is not a whole `dbf` pass either way.
SETTLE_ARM_RECREATE_CYCLES = 20886
# ...and what one `dbf` pass costs on a 68000, so a failure here reads as "the count moved by N"
# rather than as an unexplained number: 10 cycles to loop, 14 to fall out of it.
DBF_PASS_CYCLES = 10


def test_the_shifter_settle_loop_costs_our_build_exactly_what_it_was_written_at():
    # IMPORTED HERE rather than at the top, and it has to be: `bench/tier3.py` reads this module's
    # own `VERIFIED_CASES` (through `test_boot_snapshot`), so a module-level import of it would be a
    # cycle that fails at collection. By the time a test runs, both are loaded.
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
    import tier3
    from recreate_kit.rom_bench import RomBench

    measured = tier3.measure(tier3.row_named(SETTLE_ROW), RomBench())
    assert measured.recreate_cycles == SETTLE_ARM_RECREATE_CYCLES, (
        f"the monitor-change arm costs our build {measured.recreate_cycles} cycles, not the "
        f"{SETTLE_ARM_RECREATE_CYCLES} it was written at — a difference of "
        f"{abs(measured.recreate_cycles - SETTLE_ARM_RECREATE_CYCLES) / DBF_PASS_CYCLES:.1f} `dbf` "
        f"passes. `vbl.c`'s SHIFTER_SETTLE_DBF_COUNT is the shifter's settling time and the ROM's "
        f"own; if the codegen around it moved instead, re-pin this and tier3's ratio together")


def test_the_stub_at_the_vector_is_the_rom_s_own_bytes():
    """`src/bios/isr.S`'s VBL stub against the ROM's own words: the two clocks and the semaphore in
    front of the `movem`, and the restore, the release and the `rte` behind it. What sits between
    them is the `jsr` into this file's C core, which is the whole of what a transcription of a
    handler can legitimately not have."""
    isr.assert_the_stub_is_the_rom_s_bytes("ISR_VBL")


