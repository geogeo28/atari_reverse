"""Shim-contract tests for the TOS traps Joust needs (tools/recreate_kit: os.h + oracle/shim.c).

Each case drives a hand-assembled 68000 stub through the oracle and asserts on the final image —
or, where the model has no honest answer, that ``emu.run`` REJECTS the run instead of trusting a
fabricated result. That rejection is the contract these tests exist to protect: a partially modeled
call that returns a plausible-looking wrong value turns a loud failure into a silent one.

The model itself, and what each trap deliberately does not capture, is written up in
``tools/recreate_kit/TRAP_MODEL.md``. Style follows ``projects/buggyboy/recreate/test/test_os.py``.
"""
import pytest

import harness
import emu
from recreate_kit import harness as kit_harness   # the memory-map vet isn't re-exported by `*`

STUB_ENTRY = 0x10000        # stubs run from here on a throwaway image copy
SCRATCH = 0x30000           # free image page (above Joust's program, below the FS regions)
NAME_PTR = SCRATCH + 0x300  # a filename string lives here, clear of the read/write buffers

# Trap selectors (docs/tos-os-calls.md).
GEMDOS_SUPER, GEMDOS_FCREATE, GEMDOS_FOPEN, GEMDOS_FCLOSE = 0x20, 0x3C, 0x3D, 0x3E
GEMDOS_FREAD, GEMDOS_FWRITE, GEMDOS_DGETDRV, GEMDOS_PTERM = 0x3F, 0x40, 0x19, 0x4C
GEMDOS_CRAWIO, CRAWIO_RAW_READ = 0x06, 0xFF   # Crawio(0xff): raw non-blocking console read
BIOS_BCONSTAT, BIOS_BCONIN, BIOS_BCONOUT = 0x01, 0x02, 0x03
XBIOS_RANDOM, XBIOS_GIACCESS = 0x11, 0x1C

BIOS_DEV_CON = 2            # os.h OS_BIOS_DEV_CON: the console
BIOS_DEV_PRINTER = 0        # any other BIOS device: the model has no keystroke state for it

PSG_MIXER = 7               # YM2149 register 7: the tone/noise enables Joust polls
PSG_SELECT_PORT = 0xFF8800  # register-select latch; reading it reads the selected register back
PSG_DATA_PORT = 0xFF8802    # data port (shim.c's off-image PSG tap logs writes here)
PSG_BLOCK_END = 0xFF8900    # the ST decodes the chip across $ff8800..$ff88ff (shim.c PSG_BLOCK_END)

# Bytes to pop after each trap: the pushed arguments plus the 2-byte selector word.
POP_BCON, POP_SUPER, POP_GIACCESS, POP_RANDOM = 4, 6, 6, 2
POP_FOPEN, POP_FCLOSE, POP_FILE_IO, POP_CRAWIO = 8, 4, 12, 4

BUF_OUTSIDE_IMAGE = 0xFFFFFFF0   # a buffer pointer far past the end of the image (os.h OS_IMAGE_SIZE)


# ---- 68000 byte-emitters (encodings proven green in buggyboy's test_os.py) ----
def _push_l(imm):   return b"\x2f\x3c" + imm.to_bytes(4, "big")    # move.l #imm,-(a7)
def _push_w(imm):   return b"\x3f\x3c" + imm.to_bytes(2, "big")    # move.w #imm,-(a7)
def _push_d6():     return b"\x3f\x06"                             # move.w d6,-(a7)  (saved handle)
def _pop(n):        return b"\xde\xfc" + n.to_bytes(2, "big")      # adda.w #n,a7
def _trap(vec):     return bytes((0x4E, 0x40 | vec))               # trap #vec
def _st_l(addr):    return b"\x23\xc0" + addr.to_bytes(4, "big")   # move.l d0,(addr).l
def _d0_to_d6():    return b"\x3c\x00"                             # move.w d0,d6
def _st_b(addr, v): return b"\x13\xfc" + bytes((0, v)) + addr.to_bytes(4, "big")  # move.b #v,(a).l
def _st_w(addr, v): return b"\x33\xfc" + v.to_bytes(2, "big") + addr.to_bytes(4, "big")  # move.w #v,(a).l
def _st_lw(addr, v): return b"\x23\xfc" + v.to_bytes(4, "big") + addr.to_bytes(4, "big")  # move.l #v,(a).l
def _ld_b(addr):    return b"\x10\x39" + addr.to_bytes(4, "big")   # move.b (addr).l,d0
def _ld_w(addr):    return b"\x30\x39" + addr.to_bytes(4, "big")   # move.w (addr).l,d0
def _ld_lw(addr):   return b"\x20\x39" + addr.to_bytes(4, "big")   # move.l (addr).l,d0
def _rts():         return b"\x4e\x75"


def _bios(fn, dev):
    return _push_w(dev) + _push_w(fn) + _trap(13) + _pop(POP_BCON)


def _super(arg):
    return _push_l(arg) + _push_w(GEMDOS_SUPER) + _trap(1) + _pop(POP_SUPER)


def _giaccess(data, reg):
    return _push_w(reg) + _push_w(data) + _push_w(XBIOS_GIACCESS) + _trap(14) + _pop(POP_GIACCESS)


def _random():
    return _push_w(XBIOS_RANDOM) + _trap(14) + _pop(POP_RANDOM)


def _crawio(w=CRAWIO_RAW_READ):
    """Crawio(w): w = 0xff reads the console, anything else is a character to write to it."""
    return _push_w(w) + _push_w(GEMDOS_CRAWIO) + _trap(1) + _pop(POP_CRAWIO)


def _fopen_like(fn, name_ptr, arg):
    """Fopen(name, mode) / Fcreate(name, attr) — same frame shape; the handle is kept in D6."""
    return (_push_w(arg) + _push_l(name_ptr) + _push_w(fn) + _trap(1) + _pop(POP_FOPEN)
            + _d0_to_d6())


def _file_io(fn, count, buf):
    """Fread / Fwrite on the handle saved in D6."""
    return (_push_l(buf) + _push_l(count) + _push_d6() + _push_w(fn) + _trap(1)
            + _pop(POP_FILE_IO))


def _fclose():
    return _push_d6() + _push_w(GEMDOS_FCLOSE) + _trap(1) + _pop(POP_FCLOSE)


def _run(code, pokes=None):
    return emu.run(harness.make_image({STUB_ENTRY: code, **(pokes or {})}), STUB_ENTRY)


def _read_l(mem, addr):
    return int.from_bytes(mem[addr:addr + 4], "big")


# ---------------------------------------------------------------------------
# Phase 1 — BIOS console input (Bconstat 0x01 / Bconin 0x02)
# ---------------------------------------------------------------------------

def test_bconstat_reports_no_key_on_a_fresh_image():
    """With nothing staged the console is idle: Bconstat returns 0, not the -1L Joust tests for."""
    mem, _, _ = _run(_bios(BIOS_BCONSTAT, BIOS_DEV_CON) + _st_l(SCRATCH) + _rts())
    assert _read_l(mem, SCRATCH) == 0


def test_bconstat_and_bconin_deliver_the_staged_key():
    """One staged keystroke: Bconstat reports ready (-1L) and Bconin returns scancode<<16 | ascii —
    the longword shape Joust's `cmp.l #$ffffffff` and `cmp.b #$31` both read."""
    scancode = 0x02                                        # IKBD scancode for the '1' key
    code = (_bios(BIOS_BCONSTAT, BIOS_DEV_CON) + _st_l(SCRATCH)
            + _bios(BIOS_BCONIN, BIOS_DEV_CON) + _st_l(SCRATCH + 4) + _rts())
    mem, _, _ = _run(code, harness.console_key("1", scancode))
    assert _read_l(mem, SCRATCH) == 0xFFFFFFFF, "Bconstat should report a character waiting"
    assert _read_l(mem, SCRATCH + 4) == (scancode << 16) | ord("1")


def test_bconin_consumes_the_staged_key():
    """One poke is one keypress: after Bconin the console is idle again, so a polling loop like
    hiscore_key_input's sees the letter exactly once instead of holding it down forever."""
    code = (_bios(BIOS_BCONIN, BIOS_DEV_CON)
            + _bios(BIOS_BCONSTAT, BIOS_DEV_CON) + _st_l(SCRATCH) + _rts())
    mem, _, _ = _run(code, harness.console_key("A"))
    assert _read_l(mem, SCRATCH) == 0, "the key should have been consumed by Bconin"
    assert _read_l(mem, harness.OS_CON_PENDING) == 0


def test_bconin_with_no_key_pending_is_rejected():
    """Real Bconin BLOCKS until a key arrives and there is nothing here to wait for, so the model
    refuses rather than inventing a character."""
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(_bios(BIOS_BCONIN, BIOS_DEV_CON) + _rts())


@pytest.mark.parametrize("fn", (BIOS_BCONSTAT, BIOS_BCONIN))
def test_bios_console_calls_on_another_device_are_rejected(fn):
    """Only the console has modeled keystroke state; a read from any other BIOS device would be a
    fabricated answer, so the run is rejected instead."""
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(_bios(fn, BIOS_DEV_PRINTER) + _rts(), harness.console_key("A"))


def test_unmodeled_bios_selector_is_rejected():
    """The BIOS branch models exactly two selectors; Bconout and everything else still raise."""
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(_bios(BIOS_BCONOUT, BIOS_DEV_CON) + _rts())


# GEMDOS Crawio (0x06) is the console's third door. Joust never issues it (its selector census is in
# project.toml) — these pin the KIT's model, which BuggyBoy does reach, because the kit's own
# test/ runs without an oracle build or a bound project and so cannot drive a stub.

def test_crawio_reports_no_key_on_a_fresh_image():
    """A raw non-blocking read of an idle console is 0 — the value BuggyBoy's check_abort and
    console_scancode hardcode (os.h OS_CRAWIO_RESULT), so the two sides still agree by default."""
    mem, _, _ = _run(_crawio() + _st_l(SCRATCH) + _rts())
    assert _read_l(mem, SCRATCH) == 0


def test_crawio_returns_and_consumes_the_staged_key():
    """Crawio reads the SAME poked console state as Bconstat/Bconin instead of being a second,
    disconnected model: one staged key is visible to every console call and is consumed once, which
    is what a real run does. Unlike Bconin it never refuses — "no key" is a legitimate answer for a
    non-blocking read."""
    scancode = 0x1E                                        # IKBD scancode for the 'A' key
    code = _crawio() + _st_l(SCRATCH) + _crawio() + _st_l(SCRATCH + 4) + _rts()
    mem, _, _ = _run(code, harness.console_key("a", scancode))
    assert _read_l(mem, SCRATCH) == (scancode << 16) | ord("a")
    assert _read_l(mem, SCRATCH + 4) == 0, "the raw read consumes the key, like the real one"
    assert _read_l(mem, harness.OS_CON_PENDING) == 0


def test_crawio_writing_a_character_does_not_eat_the_staged_key():
    """Crawio's argument picks the DIRECTION: only 0xff reads. Any other value writes that character
    to the console — no image effect and no keystroke consumed. Servicing every Crawio as a read
    would let a program that merely prints a character swallow the key a later Bconin waits for,
    turning a staged input into a rejected run."""
    code = _crawio(ord("A")) + _st_l(SCRATCH) + _crawio() + _st_l(SCRATCH + 4) + _rts()
    mem, _, _ = _run(code, harness.console_key("z"))
    assert _read_l(mem, SCRATCH) == 0, "the output form reports no key"
    assert _read_l(mem, SCRATCH + 4) == ord("z"), "the key must still be there for the read form"


# ---------------------------------------------------------------------------
# Phase 2 — GEMDOS Super (0x20), a token model
# ---------------------------------------------------------------------------

def test_super_enters_and_restores_with_the_token():
    """Super(0) hands back the cookie and Super(cookie) is accepted as the matching restore —
    the save-and-pass-back shape of Joust's floppy routine at 0x152ea/0x15480."""
    code = (_super(0) + _st_l(SCRATCH)
            + _super(harness.OS_SUPER_TOKEN) + _st_l(SCRATCH + 4) + _rts())
    mem, _, _ = _run(code)
    assert _read_l(mem, SCRATCH) == harness.OS_SUPER_TOKEN
    assert _read_l(mem, SCRATCH + 4) == 0, "a restore reports success"


def test_super_inquire_reports_supervisor_mode():
    """Super(1) is SUP_INQUIRE. The oracle runs the whole program in supervisor mode, so -1 is the
    truthful answer about the modeled CPU."""
    mem, _, _ = _run(_super(1) + _st_l(SCRATCH) + _rts())
    assert _read_l(mem, SCRATCH) == 0xFFFFFFFF


def test_super_restore_of_a_foreign_stack_is_rejected():
    """Only a cookie the model itself issued can be honoured; any other stack pointer means the
    program is doing something the token model does not represent."""
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(_super(0x00012346) + _rts())


# ---------------------------------------------------------------------------
# Phase 3 — XBIOS Giaccess (0x1c) over the in-image YM2149 register file
# ---------------------------------------------------------------------------

def test_giaccess_read_of_a_fresh_image_is_zero():
    """The model asserts nothing about the chip's power-on contents: a fresh image reads 0, and a
    test whose control flow depends on a register states it with harness.psg_regs()."""
    mem, _, _ = _run(_giaccess(0, PSG_MIXER) + _st_l(SCRATCH) + _rts())
    assert _read_l(mem, SCRATCH) == 0


def test_giaccess_reads_the_staged_register_file():
    """A read zero-extends the staged register byte into D0."""
    mem, _, _ = _run(_giaccess(0, PSG_MIXER) + _st_l(SCRATCH) + _rts(),
                     harness.psg_regs({PSG_MIXER: 0xFF}))
    assert _read_l(mem, SCRATCH) == 0xFF


def test_giaccess_write_lands_in_the_image_and_reads_back():
    """Bit 7 of the register argument selects a write. It updates plain image state, so the write
    is covered by the differential rather than vanishing off-image the way Dosound does."""
    tone_ab_on = 0x3C                                       # snd_tone_sweep's mixer value
    code = (_giaccess(tone_ab_on, PSG_MIXER | harness.OS_PSG_WRITE)
            + _giaccess(0, PSG_MIXER) + _st_l(SCRATCH) + _rts())
    mem, _, _ = _run(code)
    assert mem[harness.OS_PSG_REGS + PSG_MIXER] == tone_ab_on, "the write must land in the image"
    assert _read_l(mem, SCRATCH) == tone_ab_on


def test_giaccess_masks_the_register_number_to_the_chips_16():
    """The register number is the low 4 bits of the argument; the YM2149 has no more than 16."""
    code = _giaccess(0x5A, harness.OS_PSG_WRITE | (PSG_MIXER + harness.OS_PSG_NREGS)) + _rts()
    mem, _, _ = _run(code)
    assert mem[harness.OS_PSG_REGS + PSG_MIXER] == 0x5A


def test_giaccess_after_a_direct_psg_write_is_rejected():
    """The register file is fed by Giaccess only, while a direct $ff8802 write goes to the shim's
    off-image ledger. A run using both would be served a read from a file it has left stale, so the
    whole run is rejected instead. Joust reaches exactly this: its floppy routine at image 0x1553c
    rewrites PSG port A directly while its sound driver uses Giaccess."""
    with pytest.raises(RuntimeError, match=r"PSG ports"):
        _run(_st_b(PSG_DATA_PORT, 0x3F) + _giaccess(0, PSG_MIXER) + _rts())


def test_giaccess_after_a_direct_psg_read_is_rejected():
    """A direct read of the select port is not modeled either (it returns 0), so it must count
    towards the same guard — otherwise Joust's `move.b $ff8800,d1` read-modify-write could be
    followed by a Giaccess served from a register file that never saw it."""
    with pytest.raises(RuntimeError, match=r"PSG ports"):
        _run(_ld_b(PSG_SELECT_PORT) + _giaccess(0, PSG_MIXER) + _rts())


def test_the_psg_select_latch_does_not_leak_between_runs():
    """`emu.psg_writes()` attributes each data byte to the last-selected register, and that latch is
    ORACLE state, not image state. Without a per-run reset, a run whose first PSG touch is a bare
    data write inherits the previous run's selection — so which register a write is credited to
    depends on what else the worker ran first, which under `pytest -n auto` is not deterministic."""
    _run(_st_b(PSG_SELECT_PORT, PSG_MIXER) + _rts())    # selects register 7, writes no data
    _run(_st_b(PSG_DATA_PORT, 0x3F) + _rts())           # a bare data write, in a FRESH run
    assert emu.psg_writes() == [(0, 0x3F)], "the second run must start from a cleared latch"


def test_every_applicable_rejection_cause_is_named():
    """A run can hit more than one reason its result is fabricated, and they are independent
    counters. Reporting only the first sends the reader off to fix that one and meet the identical
    message again — here an unmodeled BIOS selector alongside a mixed-path PSG run."""
    code = (_st_b(PSG_DATA_PORT, 0x3F) + _giaccess(0, PSG_MIXER)
            + _bios(BIOS_BCONOUT, BIOS_DEV_CON) + _rts())
    with pytest.raises(RuntimeError) as rejection:
        _run(code)
    message = str(rejection.value)
    assert "has no model" in message, f"the unmodeled BIOS selector went unnamed: {message}"
    assert "PSG ports" in message, f"the mixed PSG paths went unnamed: {message}"


@pytest.mark.parametrize("port", (PSG_SELECT_PORT, PSG_DATA_PORT))
def test_a_direct_psg_read_is_rejected_on_its_own(port):
    """A direct port read has no modeled answer at all — the ledger records writes only, so reading
    back the selected register would have to be invented — and it used to be SERVED as 0. Joust's
    drive-select does `move.b $ff8800,d1; move.b d1,d2; and.b #$f8,d1; or.b d0,d1;
    move.b d1,$ff8802` at image 0x15544: served a 0, port A's preserved upper bits are forced to
    zero, and a run using only the direct path never trips the mixed-path guard — so a
    reconstruction of that routine could be marked verified against a fabricated read. It must raise
    instead. Because this rejection stands alone, the enclosing floppy routine at 0x152dc is
    unverifiable under the oracle at all (STATUS.md)."""
    with pytest.raises(RuntimeError, match=r"PSG ports"):
        _run(_ld_b(port) + _rts())


# One access per memory callback the byte path used to be alone in guarding — 16- and 32-bit, read
# and write. `move.w #$0e00,$ff8800` is the idiom that motivates this; the rest keep each callback's
# tap individually pinned, so removing any one of them fails a named case.
WIDE_PSG_ACCESSES = (
    ("write.w select", _st_w(PSG_SELECT_PORT, 0x0E00)),
    ("write.w data", _st_w(PSG_DATA_PORT, 0x0E00)),
    ("write.l spanning both", _st_lw(PSG_SELECT_PORT, 0x0E000E00)),
    ("read.w select", _ld_w(PSG_SELECT_PORT)),
    ("read.l spanning both", _ld_lw(PSG_SELECT_PORT)),
    # The odd aliases: a byte write there matches neither port exactly, so it used to be dropped
    # by the same equality test the wide accesses slipped past.
    ("write.b select+1", _st_b(PSG_SELECT_PORT + 1, 0x3F)),
    ("write.b data+1", _st_b(PSG_DATA_PORT + 1, 0x3F)),
    # A mirror: the ST decodes the YM2149 incompletely, so it answers across $ff8800..$ff88ff.
    ("write.b a mirror", _st_b(PSG_SELECT_PORT + 4, 0x07)),
    ("read.b a mirror", _ld_b(PSG_BLOCK_END - 1)),
)


@pytest.mark.parametrize("code", [c for _, c in WIDE_PSG_ACCESSES],
                         ids=[name for name, _ in WIDE_PSG_ACCESSES])
def test_a_wide_access_to_the_psg_ports_is_rejected(code):
    """Only the BYTE protocol (select latch, then data) is modeled. A `move.w #$0e00,$ff8800` slips
    past a byte callback that compares the address for equality, reaching neither the ledger nor the
    direct-path tally — which would silently DISARM the mixed-path guard, since such a run could
    then be combined with Giaccess. Tallying it in every callback width is what stops that."""
    with pytest.raises(RuntimeError, match=r"PSG ports"):
        _run(code + _rts())


# snd_poll_done @ 0x10a8a reads the mixer and releases the sound priority when every tone and noise
# enable is off — the read steers control flow, so it is the model's real acceptance test.
SND_POLL_DONE = 0x10A8A
A_SND_PRIORITY = 0x10D4C          # names.txt: snd_priority
SND_PRIORITY_IDLE = 0x10          # what snd_poll_done stores once the sound has finished
SND_MIXER_ALL_OFF = 0x3F          # every tone + noise enable set = silence


@pytest.mark.parametrize("mixer, released", [(SND_MIXER_ALL_OFF, True), (0x3C, False), (0x00, False)])
def test_snd_poll_done_follows_the_staged_mixer(mixer, released):
    """Joust's own function, run under the oracle: the staged register 7 decides whether it releases
    snd_priority. Both branches must be reachable purely by poking the register file."""
    busy = 0x0003                                           # a sound in progress holds a priority
    pokes = {A_SND_PRIORITY: busy.to_bytes(2, "big"), **harness.psg_regs({PSG_MIXER: mixer})}
    mem, _, _ = emu.run(harness.make_image(pokes), SND_POLL_DONE)
    expected = SND_PRIORITY_IDLE if released else busy
    assert int.from_bytes(mem[A_SND_PRIORITY:A_SND_PRIORITY + 2], "big") == expected


# ---------------------------------------------------------------------------
# Phase 4 — GEMDOS Fcreate (0x3c) + Fwrite (0x40)
# ---------------------------------------------------------------------------

HISCORE_FILE, HISCORE_LEN = "HIGH.SCO", 0x1A     # what poll_quit_key writes on Ctrl-C


def test_fcreate_write_close_reopen_read_round_trip():
    """The path poll_quit_key takes: create the high-score file, write its 26 bytes, then read them
    back. Staging lives in the image, so both cores see the write and the diff covers it."""
    payload = bytes(range(1, HISCORE_LEN + 1))
    stage, handles = harness.stage_files([(HISCORE_FILE, b"", HISCORE_LEN)])
    code = (_fopen_like(GEMDOS_FCREATE, NAME_PTR, 0) + _file_io(GEMDOS_FWRITE, len(payload), SCRATCH)
            + _st_l(SCRATCH + 0x100) + _fclose()
            + _fopen_like(GEMDOS_FOPEN, NAME_PTR, 0) + _file_io(GEMDOS_FREAD, 0x40, SCRATCH + 0x40)
            + _st_l(SCRATCH + 0x104) + _fclose() + _rts())
    pokes = {NAME_PTR: HISCORE_FILE.encode() + b"\0", SCRATCH: payload, **stage}
    mem, _, _ = _run(code, pokes)
    assert handles[HISCORE_FILE] == harness.OS_FS_FIRST_HANDLE
    assert _read_l(mem, SCRATCH + 0x100) == len(payload), "Fwrite returns the byte count"
    assert _read_l(mem, SCRATCH + 0x104) == len(payload), "the re-read stops at the written length"
    assert mem[SCRATCH + 0x40:SCRATCH + 0x40 + len(payload)] == payload


def test_fcreate_truncates_an_existing_file():
    """Fcreate on a file that already has bytes resets its length to zero, so a later Fread sees
    only what was written after the create."""
    stage, _ = harness.stage_files([(HISCORE_FILE, bytes(range(HISCORE_LEN)))])
    code = (_fopen_like(GEMDOS_FCREATE, NAME_PTR, 0) + _fclose()
            + _fopen_like(GEMDOS_FOPEN, NAME_PTR, 0) + _file_io(GEMDOS_FREAD, 0x40, SCRATCH)
            + _st_l(SCRATCH + 0x100) + _fclose() + _rts())
    mem, _, _ = _run(code, {NAME_PTR: HISCORE_FILE.encode() + b"\0", **stage})
    assert _read_l(mem, SCRATCH + 0x100) == 0, "the truncated file should read as empty"
    assert mem[SCRATCH:SCRATCH + HISCORE_LEN] == bytes(HISCORE_LEN), "nothing should be copied out"


def test_fcreate_of_an_undeclared_file_is_rejected():
    """The harness declares the filesystem. There is no staging space to hand a name it never
    reserved, so the model refuses rather than inventing an address."""
    code = _fopen_like(GEMDOS_FCREATE, NAME_PTR, 0) + _rts()
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(code, {NAME_PTR: b"NOPE.SCO\0"})


def test_fwrite_past_the_staged_capacity_is_rejected():
    """A write running off the end of the reservation would overrun the next staged file. A short
    count would fabricate a disk-full result the harness has no basis for, so it raises instead."""
    stage, _ = harness.stage_files([(HISCORE_FILE, b"", HISCORE_LEN)])
    code = (_fopen_like(GEMDOS_FCREATE, NAME_PTR, 0)
            + _file_io(GEMDOS_FWRITE, HISCORE_LEN + 1, SCRATCH) + _rts())
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(code, {NAME_PTR: HISCORE_FILE.encode() + b"\0", **stage})


def test_fwrite_with_a_wrapping_count_is_rejected():
    """`count` comes straight off the emulated program's stack, so the capacity check must not be
    written as `cursor + count > capacity`: that sum wraps and would wave through a memcpy running
    off the end of the image (a segfault instead of the contract's refusal)."""
    stage, _ = harness.stage_files([(HISCORE_FILE, b"", HISCORE_LEN)])
    code = (_fopen_like(GEMDOS_FCREATE, NAME_PTR, 0) + _file_io(GEMDOS_FWRITE, 2, SCRATCH)
            + _file_io(GEMDOS_FWRITE, 0xFFFFFFFF, SCRATCH) + _rts())
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(code, {NAME_PTR: HISCORE_FILE.encode() + b"\0", **stage})


def test_a_reserved_capacity_does_not_overlap_the_next_staged_file():
    """Staging steps by each file's RESERVATION, not by the bytes it currently holds — otherwise an
    Fwrite growing the first file into the capacity it was promised would overwrite the second
    file's staged bytes, and both the write and the corrupted read would look perfectly healthy."""
    other_name, other_data = "OTHER.DAT", b"XYZ"
    other_ptr = NAME_PTR + 0x20
    stage, handles = harness.stage_files([(HISCORE_FILE, b"", HISCORE_LEN), (other_name, other_data)])
    payload = bytes(range(0x40, 0x40 + HISCORE_LEN))
    code = (_fopen_like(GEMDOS_FCREATE, NAME_PTR, 0) + _file_io(GEMDOS_FWRITE, len(payload), SCRATCH)
            + _fclose()
            + _fopen_like(GEMDOS_FOPEN, other_ptr, 0) + _file_io(GEMDOS_FREAD, 0x40, SCRATCH + 0x40)
            + _st_l(SCRATCH + 0x100) + _fclose() + _rts())
    pokes = {NAME_PTR: HISCORE_FILE.encode() + b"\0", other_ptr: other_name.encode() + b"\0",
             SCRATCH: payload, **stage}
    mem, _, _ = _run(code, pokes)
    assert handles[other_name] == harness.OS_FS_FIRST_HANDLE + 1
    assert _read_l(mem, SCRATCH + 0x100) == len(other_data)
    assert mem[SCRATCH + 0x40:SCRATCH + 0x40 + len(other_data)] == other_data


def test_staging_more_files_than_there_are_slots_is_refused():
    """The table is OS_FS_SLOTS entries long; a ninth would be written past its end, on top of the
    staging area os_fread then serves bytes from — corrupting a file rather than failing."""
    too_many = [(f"F{i}.DAT", b"x") for i in range(harness.OS_FS_SLOTS + 1)]
    with pytest.raises(AssertionError, match="slot"):
        harness.stage_files(too_many)


def test_fwrite_from_a_buffer_outside_the_image_is_rejected():
    """`buf` comes off the emulated program's stack exactly as `count` does, so it needs the same
    bound: every m68k_*_memory_* callback checks its access against the image length, and these two
    helpers memcpy without going through one."""
    stage, _ = harness.stage_files([(HISCORE_FILE, b"", HISCORE_LEN)])
    code = (_fopen_like(GEMDOS_FCREATE, NAME_PTR, 0)
            + _file_io(GEMDOS_FWRITE, 4, BUF_OUTSIDE_IMAGE) + _rts())
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(code, {NAME_PTR: HISCORE_FILE.encode() + b"\0", **stage})


def test_fread_into_a_buffer_outside_the_image_is_rejected():
    """Fread's side is the worse one: it WRITES through `buf`, so an unchecked pointer corrupts
    memory outside the image buffer rather than merely reading garbage into it."""
    stage, _ = harness.stage_files([(HISCORE_FILE, bytes(range(HISCORE_LEN)))])
    code = (_fopen_like(GEMDOS_FOPEN, NAME_PTR, 0)
            + _file_io(GEMDOS_FREAD, 4, BUF_OUTSIDE_IMAGE) + _rts())
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(code, {NAME_PTR: HISCORE_FILE.encode() + b"\0", **stage})


def test_fread_that_would_end_past_the_top_of_the_image_is_rejected():
    """The bound covers the whole transfer, not just its start: a buffer two bytes below the top of
    the image with four bytes to copy is refused, not quietly truncated to a short read."""
    stage, _ = harness.stage_files([(HISCORE_FILE, bytes(range(HISCORE_LEN)))])
    code = (_fopen_like(GEMDOS_FOPEN, NAME_PTR, 0)
            + _file_io(GEMDOS_FREAD, 4, harness.OS_IMAGE_SIZE - 2) + _rts())
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(code, {NAME_PTR: HISCORE_FILE.encode() + b"\0", **stage})


def test_fwrite_on_a_closed_handle_is_rejected():
    """Same contract as Fread: a closed handle is not silently served."""
    stage, _ = harness.stage_files([(HISCORE_FILE, b"", HISCORE_LEN)])
    code = (_fopen_like(GEMDOS_FCREATE, NAME_PTR, 0) + _fclose()
            + _file_io(GEMDOS_FWRITE, 4, SCRATCH) + _rts())
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(code, {NAME_PTR: HISCORE_FILE.encode() + b"\0", **stage})


def test_fwrite_appends_at_the_cursor():
    """Sequential Fwrites advance the same cursor the reads use, so two writes concatenate."""
    stage, _ = harness.stage_files([(HISCORE_FILE, b"", HISCORE_LEN)])
    first, second = b"AB", b"CDE"
    code = (_fopen_like(GEMDOS_FCREATE, NAME_PTR, 0)
            + _file_io(GEMDOS_FWRITE, len(first), SCRATCH)
            + _file_io(GEMDOS_FWRITE, len(second), SCRATCH + 0x10) + _fclose()
            + _fopen_like(GEMDOS_FOPEN, NAME_PTR, 0) + _file_io(GEMDOS_FREAD, 0x40, SCRATCH + 0x20)
            + _st_l(SCRATCH + 0x100) + _fclose() + _rts())
    pokes = {NAME_PTR: HISCORE_FILE.encode() + b"\0", SCRATCH: first, SCRATCH + 0x10: second,
             **stage}
    mem, _, _ = _run(code, pokes)
    assert _read_l(mem, SCRATCH + 0x100) == len(first) + len(second)
    assert mem[SCRATCH + 0x20:SCRATCH + 0x20 + 5] == first + second


# ---------------------------------------------------------------------------
# Phase 5 — XBIOS Random (0x11)
# ---------------------------------------------------------------------------

def test_random_returns_the_staged_value_masked_to_24_bits():
    """Random is a test INPUT, not a generator: it returns the staged longword, and the top byte is
    dropped because XBIOS Random yields 24 bits."""
    staged = 0xAB123456
    mem, _, _ = _run(_random() + _st_l(SCRATCH) + _rts(),
                     {harness.OS_RANDOM_VALUE: staged.to_bytes(4, "big")})
    assert _read_l(mem, SCRATCH) == staged & 0x00FFFFFF


def test_random_repeats_within_a_run():
    """Every call in one run returns the same value. A program looping until Random differs would
    spin and be rejected for exceeding its instruction cap — a loud failure, not a wrong answer."""
    code = _random() + _st_l(SCRATCH) + _random() + _st_l(SCRATCH + 4) + _rts()
    mem, _, _ = _run(code, {harness.OS_RANDOM_VALUE: (0x00C0FFEE).to_bytes(4, "big")})
    assert _read_l(mem, SCRATCH) == _read_l(mem, SCRATCH + 4) == 0x00C0FFEE


# ---------------------------------------------------------------------------
# Still unmodeled — Joust's census turns up two GEMDOS selectors outside this model's scope.
# They must keep raising: an honest rejection beats a fabricated return value.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fn", (GEMDOS_DGETDRV, GEMDOS_PTERM))
def test_out_of_scope_gemdos_selectors_still_raise(fn):
    with pytest.raises(RuntimeError, match="unmodeled"):
        _run(_push_w(fn) + _trap(1) + _pop(2) + _rts())


# ---------------------------------------------------------------------------
# The model's memory map vs THIS project — harness._vet_os_memory_map()'s two newest checks. Both
# pass for every project in the tree, so the only way to exercise them is to state the offending
# configuration directly; same reasoning as test_heap_guard.py, which pins the kit's other guard.
# ---------------------------------------------------------------------------

def test_a_program_loading_over_the_poked_input_block_is_refused(monkeypatch):
    """The block's "below every program" siting rested on a load_base read verbatim from
    project.toml: a project loading below 0x620 would have its keystroke/Random/PSG pokes land on
    its own code with no diagnostic at all."""
    monkeypatch.setattr(kit_harness.loader, "LOAD_BASE", harness.OS_POKE_BLOCK_END - 2)
    with pytest.raises(RuntimeError, match="poked input block"):
        kit_harness._vet_os_memory_map()


def test_an_image_size_that_disagrees_with_os_h_is_refused(monkeypatch):
    """os_fread/os_fwrite bound their copies against os.h's OS_IMAGE_SIZE, which no project.toml
    feeds. A larger real image would leave the top unreachable; a smaller one would let a copy run
    past the end of the buffer."""
    monkeypatch.setattr(kit_harness.loader, "IMAGE_SIZE", harness.OS_IMAGE_SIZE * 2)
    with pytest.raises(RuntimeError, match="OS_IMAGE_SIZE"):
        kit_harness._vet_os_memory_map()
