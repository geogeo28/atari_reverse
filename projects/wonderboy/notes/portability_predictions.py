#!/usr/bin/env python3
"""Run the static portability classification against the real oracle, and fail if it is wrong.

`recreate/PORTABILITY.md` sorts every function of SWB.PRG into tiers by reading its hardware
accesses out of Ghidra. That is a PREDICTION about what `tools/recreate_kit`'s Musashi oracle
will do — so each case below states the prediction, runs the original 68000 code under the
oracle, and checks the prediction actually happens. A failing case means the classifier is
wrong, not that the oracle is.

What each tier is predicted to do (the rules are in tools/hw_portability.py):
  T0  runs to `rts`, touching nothing off-image.
  T2  runs to `rts`; every hardware write is silently DROPPED, so it can produce an EMPTY
      write set while doing its whole job on real hardware.
  T3  runs to `rts` — but every non-PSG hardware read returns 0, so the code takes whichever
      branch a permanently-zero read implies. That is the false green: the same wrong value is
      served to both sides of a differential, so the diff agrees on a fiction.
  T4  is REFUSED by `emu.run`, which raises rather than verify against a fabricated PSG read.

TWO CORRECTIONS THIS FILE FORCED ON THE FIRST DRAFT OF THE CLASSIFICATION. Neither moved a
function's TIER — `fdc_wait_irq` was T3-STEER and `snd_music_tick` T4 under both drafts, and the
classifier in tools/hw_portability.py did not change. What they corrected is the PROSE: what a
tier was claimed to MEAN when the code actually runs.

  * The FDC poll does not spin to its timeout, it succeeds INSTANTLY. `btst #5,$fffa01 / bne` loops
    while the bit is SET; the MFP GPIP FDC line is ACTIVE LOW, so a permanent 0 reads as "the
    controller has already finished". A T3 read is not "the code hangs", it is "the code believes
    whatever 0 means", and here 0 means "done". NOTE the limit the FDC command cases below then
    put on that: the POLLS report success, the COMMANDS built on them report hard failure.
  * A T4 function is only rejected on a run that REACHES its PSG access. snd_music_tick is T4 by
    code, yet returns green from the image's own initial state because the music-playing test two
    instructions later exits early. So T4 states "cannot be verified across its inputs", not "every
    run is refused" — a case selection that misses the access gets a green that proves nothing.

Usage: portability_predictions.py
Exit status: 0 every prediction held · 1 at least one did not
"""
import pathlib
import re
import struct
import sys

REVERSE = pathlib.Path(__file__).resolve().parents[3]
RECREATE = pathlib.Path(__file__).resolve().parents[1] / "recreate"
sys.path.insert(0, str(REVERSE / "tools"))
from recreate_kit import project                                  # noqa: E402

# Binds loader.LOAD_BASE / loader.IMAGE_SIZE from recreate/project.toml. Must happen before `emu`
# is imported: emu derives its stack constants from loader.IMAGE_SIZE at import time.
CONFIG = project.load(RECREATE)
import loader                                                     # noqa: E402
try:
    import emu                                                    # noqa: E402
except OSError as err:                                            # the ctypes.CDLL at emu import
    sys.exit("cannot load the kit's Musashi oracle (%s)\nbuild it first: "
             "make -C projects/wonderboy/recreate oracle" % err)

IMAGE = loader.load_image(CONFIG.prg)

# The PSG rejection `emu.run` raises for a T4 function. Matched rather than merely expecting SOME
# RuntimeError, so a case that fails for an unrelated reason (a stray unmodeled trap, a run that
# never returns) cannot pass for a correct T4 prediction.
PSG_REJECT = re.compile(r"accessed the PSG ports .* cannot serve")

# The two software timeouts the FDC poll loops carry, read off the code (`move.l #imm,d7`):
# fdc_wait_irq/fdc_wait_irq_bounded count 600,000 and fdc_restore 300,000. Under the oracle the
# MFP bit they wait on is always 0, so these are not a bound — they are the whole run.
FDC_POLL_TIMEOUT = 600_000
FDC_RESTORE_TIMEOUT = 300_000
# Where each poll goes when its counter runs out. Both funnel into floppy_unwind_return, which
# writes an error code into the driver's state block — the one image byte that separates the two
# outcomes, since everything else the loops touch is hardware.
FDC_WAIT_IRQ_TIMEOUT_PC = 0x62FC
FDC_WAIT_IRQ_ERROR = 0xFFFF
FDC_RESTORE_TIMEOUT_PC = 0x6444
FDC_RESTORE_ERROR = 0xFFFB
FLOPPY_UNWIND_RETURN = 0x644E    # past it, A7 is reloaded from a slot that is 0 in a fresh image
# The two COMMAND-level driver entries built on those polls, and the error code each returns when
# the fabricated status byte fails its acceptance test. Both funnel into floppy_unwind_return, so
# both are run to that checkpoint rather than to an rts.
FN_FDC_READ_ADDRESS_CMD = 0x63C0
FDC_READ_ADDRESS_ERROR = 0xFFFB
PC_FDC_READ_ADDRESS_RETRY = 0x63F8
FN_FDC_READ_SECTOR_CMD = 0x6488
FDC_READ_SECTOR_ERROR = 0xFFFD
PC_FDC_READ_SECTOR_RETRY = 0x64DA
# The two PC_*_RETRY above are each command's `subq.w #1,fdc_retry_count` — the instruction only a
# run that REJECTED the status byte executes, and therefore the control (see the helper's docstring
# for why the counter's presence in the write set is not one). fdc_retry_count is $6526.

# Big enough that "spun to its software timeout" is distinguishable from "hung": every case below
# reports the instructions it really used, and a hang shows up as the RuntimeError emu.run raises.
MAX_INSNS = 40_000_000

# Scratch addresses for the T0 case, clear of the program (0x3f8..0x218d0) and of the oracle's
# stack guard — see recreate/project.toml's memory map.
SCRATCH_SRC = 0x40000
SCRATCH_DST = 0x41000
COPY_LONGS = 8                       # copy_longs takes count-1 in D0

# The addresses under test, all runtime addresses at load_base 0x3f8 (see ../names.txt).
FN_COPY_LONGS = 0xF93C
FN_VIDEO_SET_LOWRES_50HZ = 0xF906
FN_CLEAR_PALETTE = 0xE7F4
# Each T2 function's LAST hardware write. Asserting the run REACHED it is the positive control the
# T2 cases need: the shim drops every off-image write, so "completed with zero image writes" is
# equally what a bare `rts` produces, and without this a T2 case passes for a function that did
# nothing at all. (Verified by mutation: pointing FN_CLEAR_PALETTE at the bare `rts` at $62fa
# leaves the image untouched and is caught here, not by the write set.)
PC_VIDEO_SET_LOWRES_LAST_HW_WRITE = 0xF91C     # move.b #2,$ff820a, 4th of its 4 shifter writes
PC_CLEAR_PALETTE_LAST_HW_WRITE = 0xE808        # 8th `clr.l (a0)+`, into $ff825c
FN_FDC_WAIT_IRQ = 0x62D0
FN_FDC_RESTORE = 0x6408
FN_IKBD_DISABLE_MOUSE = 0xF8F0
FN_PSG_SET_DRIVE_SELECT = 0x624C
FN_SND_PSG_READ_MODIFY = 0x17F24
FN_SND_MUSIC_TICK = 0x17C74
# snd_music_tick's tempo byte: `lea $1738c(pc),a3` then `move.b #imm,2274(a3)`.
SND_TEMPO_ADDR = 0x1738C + 2274
SND_TEMPO_MONO = 0x48                # the branch a zeroed MFP GPIP bit 7 forces
SND_TEMPO_60HZ = 0x2B                # the branch a colour ST at 60 Hz sync would take instead
# The sound module's effect-trigger entry stub and the routine behind it (334 B). T0 CLEAN with an
# EXACT closure (nothing in the subtree touches hardware and it holds no unresolved indirect site),
# so it is the counter-example to "no byte of the sound subsystem is verifiable at all". Entered
# through the stub because that is how the game reaches it.
FN_SND_TRIGGER_STUB = 0x17B14
FN_SND_TRIGGER_EFFECT = 0x1A48A

# The background scroll blitter, the second unrolled blit family (../names.txt). Variant 0 copies
# 30 longwords per scanline out of a 128-byte-wide source row into a 160-byte screen line, twice:
# d7+1 rows, then — because d6 >= 0 — d6+1 more after rewinding a0 by the source buffer's height.
FN_BG_SCROLL_COPY_X0 = 0x83B6
BG_SCROLL_BYTES_PER_ROW = 120        # 30 x `move.l (a0)+,(a1)+`
BG_SCROLL_DEST_STRIDE = 160          # one 320-pixel 4-plane scanline
BG_SCROLL_SRC_ROW_STRIDE = 128       # the 120 copied bytes plus the `addq.l #8,a0` at the row end
BG_SCROLL_SRC_WRAP = 22528           # `lea -$5800(a0),a0`: the 176-row source buffer's height
# The jump table those 16 routines hang off, and the names.txt prefix whose entries must equal it.
# Nothing else pins 15 of the 16 names: only variant 0 is executed below, and Ghidra builds no call
# edge through a `jmp (a2)`, so without this check a mis-transcribed address would survive a
# re-bootstrap silently and still be counted as a measured, T0, "start here" function.
BG_SCROLL_TABLE_ADDR = 0x8366
BG_SCROLL_VARIANTS = 16
BG_SCROLL_NAME_PREFIX = "bg_scroll_copy_x"


def run(entry, regs=None, max_insns=MAX_INSNS, stop_pc=0, image=None):
    """One oracle run on a fresh copy of the image, or of `image` when a case seeded bytes first.

    Mirrors `emu.run`'s own signature so every case can go through here: a run that stops at a
    checkpoint instead of an rts is the normal shape for this driver, whose error path never
    returns (FLOPPY_UNWIND_RETURN).
    """
    return emu.run(bytearray(IMAGE if image is None else image), entry, regs=regs or {},
                   max_insns=max_insns, stop_pc=stop_pc)


def run_reaching(entry, witness_pc, **kwargs):
    """Run `entry` with PC coverage on, and report whether execution reached `witness_pc`.

    The positive control a case needs whenever its outcome is an ABSENCE — no image write, an
    error code, an empty ledger — because an absence is also what a function that did nothing
    produces. `witness_pc` is the instruction that proves the body really ran.
    """
    emu.cov_enable()
    emu.cov_reset()
    try:
        mem, writes, out = run(entry, **kwargs)
    finally:
        emu.cov_enable(False)
    return mem, writes, out, emu.cov_visited(witness_pc)


def image_writes(writes):
    """Writes to the program's own address space, i.e. what a memory differential would compare.

    The oracle's write log includes the call frame it pushes for us, which is not the function's
    output; the kit excludes the same band when it diffs (emu.STACK_GUARD_LO upwards).
    """
    return {a for a in writes if a < emu.STACK_GUARD_LO}


def case_t0_copy_longs():
    """T0 CLEAN: a pure memcpy. Completes, and every byte it writes is inside the image."""
    _, writes, out = run(FN_COPY_LONGS, {"a0": SCRATCH_SRC, "a1": SCRATCH_DST,
                                         "d0": COPY_LONGS - 1})
    written = image_writes(writes)
    expected = set(range(SCRATCH_DST, SCRATCH_DST + COPY_LONGS * 4))
    if written != expected:
        return False, ("copy_longs wrote %d image byte(s), expected exactly the %d-byte "
                       "destination" % (len(written), COPY_LONGS * 4))
    return True, "copy_longs: %d insns, wrote exactly its %d-byte destination" % (out["ninsns"],
                                                                                  COPY_LONGS * 4)


def _t2_did_its_whole_job_off_image(name, entry, last_hw_write_pc, detail):
    """A T2 function must do BOTH things: execute its hardware writes, and leave the image alone.

    Checking only the second half is what let a bare `rts` pass, so the coverage control comes
    first and its failure is reported as the classification being unproven, not as a clean run.
    """
    _, writes, out, reached = run_reaching(entry, last_hw_write_pc)
    if not reached:
        return False, ("%s never reached its hardware write at %#x, so 'zero image writes' proves "
                       "nothing about it" % (name, last_hw_write_pc))
    written = image_writes(writes)
    if written:
        return False, ("%s wrote %d image byte(s); the classification says its whole effect is "
                       "off-image" % (name, len(written)))
    return True, "%s: %d insns, reached %#x, ZERO image writes — %s" % (name, out["ninsns"],
                                                                       last_hw_write_pc, detail)


def case_t2_video_set_lowres():
    """T2 HW_WRITE_ONLY: four shifter writes and NOTHING else — so under the oracle this function
    does its entire job and leaves the image byte-identical. A differential over it is vacuous."""
    return _t2_did_its_whole_job_off_image(
        "video_set_lowres_50hz", FN_VIDEO_SET_LOWRES_50HZ, PC_VIDEO_SET_LOWRES_LAST_HW_WRITE,
        "resolution, screen base and 50 Hz sync all dropped, so the diff is empty either way")


def case_t2_clear_palette():
    """T2 through a REGISTER-INDIRECT idiom (`lea $ff8240,a0` then `clr.l (a0)+`), the case an
    operand scan cannot see. Same outcome: the run completes and writes no image byte."""
    return _t2_did_its_whole_job_off_image(
        "clear_palette", FN_CLEAR_PALETTE, PC_CLEAR_PALETTE_LAST_HW_WRITE,
        "8 longwords into $ff8240 through an address register, all dropped")


def _poll_took_the_success_path(name, entry, fail_pc, fail_status, timeout):
    """Both FDC poll loops end one of two ways, and the two are separable in the image alone:

      success  `exg d1,d7 / rts`            — D0 untouched (0) and NOT ONE image byte written;
      timeout  `bra floppy_unwind_return`   — D0 := an error code, then the driver's error byte.

    So this asserts the success signature, then runs the timeout branch DIRECTLY as a negative
    control and requires D0 to come back as that branch's error code. Without the control,
    "D0 == 0 and no image writes" could be the signature of both paths and the case would pass
    for the wrong reason. The control stops AT floppy_unwind_return, because past that point the
    routine reloads A7 from a saved slot that is zero in a freshly loaded image and never returns.
    """
    _, writes, out = run(entry, max_insns=timeout * 8)
    written = image_writes(writes)
    if written or out["d0"] != 0:
        return False, ("%s took the TIMEOUT path (d0=%#x, %d image write(s)); the classification "
                       "predicts the zeroed MFP bit reads as 'already done'"
                       % (name, out["d0"], len(written)))
    _, _, fail_out = emu.run(bytearray(IMAGE), fail_pc, max_insns=timeout * 8,
                             stop_pc=FLOPPY_UNWIND_RETURN)
    if fail_out["d0"] != fail_status:
        return False, ("the timeout branch at %#x came back d0=%#x, not its error code %#x, so "
                       "this case cannot tell the two outcomes apart"
                       % (fail_pc, fail_out["d0"], fail_status))
    return True, ("%s: %d insns, d0=0, zero image writes — it reports a complete, error-free "
                  "transfer on its FIRST status test, having moved nothing. Its timeout branch "
                  "at %#x is reachable and returns d0=%#x." % (name, out["ninsns"], fail_pc,
                                                               fail_status))


def case_t3_fdc_wait_irq():
    """T3-STEER: `btst #5,$fffa01` waiting for the FDC interrupt. The line is ACTIVE LOW, so the
    oracle's permanent 0 means "already done" and the 600,000-iteration timeout is never
    approached — the poll passes on its first test. What the COMMANDS above it then do with that
    fabricated success is the pair of cases below; the two halves disagree."""
    return _poll_took_the_success_path("fdc_wait_irq", FN_FDC_WAIT_IRQ, FDC_WAIT_IRQ_TIMEOUT_PC,
                                       FDC_WAIT_IRQ_ERROR, FDC_POLL_TIMEOUT)


def case_t3_fdc_restore():
    """T3-STEER: the same shape in fdc_restore, whose seek-complete poll likewise passes at once,
    after which a WD1772 status read that is also permanently 0 reads as "no error"."""
    return _poll_took_the_success_path("fdc_restore", FN_FDC_RESTORE, FDC_RESTORE_TIMEOUT_PC,
                                       FDC_RESTORE_ERROR, FDC_RESTORE_TIMEOUT)


def _fdc_command_reports_hard_failure(name, entry, error_status, retry_pc):
    """The poll succeeding instantly does NOT make the driver report success.

    fdc_wait_irq returns the WD1772 status byte it read back through $ff8604, which the oracle
    also answers 0 — and 0 fails each command's acceptance test (`andi.b #$f9 / cmp.b #$a0` here,
    `cmp.b #$80` there). So the command retries fdc_retry_count times and returns an error, having
    moved image state on the way. Run to floppy_unwind_return, past which A7 is reloaded from a
    slot that is zero in a fresh image.

    The control is `retry_pc`, the `subq.w #1,fdc_retry_count` inside the retry path, and it has to
    be: "fdc_retry_count is in the write set" would be vacuous, because the command's FIRST
    instruction is `move.w #$2,fdc_retry_count` and puts it there whatever happens afterwards.
    """
    _, writes, out, retried = run_reaching(entry, retry_pc, stop_pc=FLOPPY_UNWIND_RETURN)
    status = out["d0"] & 0xFFFF                     # `move.w #imm,d0` leaves the high word alone
    written = image_writes(writes)
    if status != error_status:
        return False, ("%s returned d0.w=%#x, not the error code %#x its fabricated-status path "
                       "should reach" % (name, status, error_status))
    if not retried:
        return False, ("%s reached the error return without executing the retry decrement at %#x, "
                       "so it did not fail the way this case claims" % (name, retry_pc))
    return True, ("%s: %d insns, d0.w=%#x (ERROR) after exhausting the retries at %#x, %d image "
                  "write(s) — the poll below it reports instant success, the COMMAND reports hard "
                  "failure and still moves image state"
                  % (name, out["ninsns"], status, retry_pc, len(written)))


def case_t3_fdc_read_address_command():
    """The command level of the same driver the two poll cases above measure. It is the half that
    decides what a reconstruction of disk_load_file would be diffed against."""
    return _fdc_command_reports_hard_failure("fdc read-address command", FN_FDC_READ_ADDRESS_CMD,
                                             FDC_READ_ADDRESS_ERROR, PC_FDC_READ_ADDRESS_RETRY)


def case_t3_fdc_read_sector_command():
    """The sector-read command, whose acceptance test is `cmp.b #$80,d7` on the same zeroed status.
    It writes the DMA address longword as well as the retry counter before giving up."""
    return _fdc_command_reports_hard_failure("fdc read-sector command", FN_FDC_READ_SECTOR_CMD,
                                             FDC_READ_SECTOR_ERROR, PC_FDC_READ_SECTOR_RETRY)


def case_t3_ikbd_disable_mouse():
    """T3-STEER where the shim's ONE modeled read flips the outcome the other way: the ACIA
    status is answered IKBD_TX_RDY, so the transmit-ready poll succeeds on its first pass and the
    command byte is then dropped. The run is green, fast, and proves nothing about the IKBD."""
    _, writes, out = run(FN_IKBD_DISABLE_MOUSE)
    written = image_writes(writes)
    if written:
        return False, "ikbd_disable_mouse wrote %d image byte(s), expected none" % len(written)
    if out["ninsns"] > FDC_POLL_TIMEOUT:
        return False, ("ikbd_disable_mouse spun %d insns; the shim's IKBD_TX_RDY special case is "
                       "supposed to let it out immediately" % out["ninsns"])
    return True, ("ikbd_disable_mouse: %d insns — the poll exits at once because the shim answers "
                  "the ACIA status $02, and the $12 command byte is then dropped" % out["ninsns"])


def expect_psg_rejection(name, entry):
    try:
        run(entry)
    except RuntimeError as err:
        if PSG_REJECT.search(str(err)):
            return True, "%s: refused, '%s'" % (name, str(err).split(": ", 1)[-1][:96])
        return False, "%s raised, but not the PSG diagnostic: %s" % (name, err)
    return False, "%s COMPLETED — the classifier says it is a hard reject" % name


def case_t4_psg_set_drive_select():
    """T4: the drive-select read-modify-write of PSG port A. `move.b $ff8800,d1` is a PSG READ,
    which the shim refuses outright — so the whole floppy stack above it can never run."""
    return expect_psg_rejection("psg_set_drive_select", FN_PSG_SET_DRIVE_SELECT)


def case_t4_sound_psg_read():
    """T4 in the OTHER subsystem: the sound module's read-modify-write of the mixer register."""
    return expect_psg_rejection("FUN_00017f24 (sound)", FN_SND_PSG_READ_MODIFY)


def case_t3_music_tempo_is_chosen_by_a_zeroed_read():
    """BuggyBoy's defect, in this game, demonstrated end to end.

    snd_music_tick opens by picking the replay tempo from TWO hardware reads —
    `btst #7,$fffa01` (MFP GPIP bit 7, the monochrome-monitor detect) and, failing that,
    `btst #1,$ff820a` (the 50/60 Hz sync register) — and stores the answer in SND_TEMPO_ADDR.
    Both read 0 under the oracle, so the mono-monitor branch is taken unconditionally and the
    byte lands on SND_TEMPO_MONO. On a colour ST, GPIP bit 7 is high and this branch is dead
    code. Nothing in a memory differential can tell: both sides store the same wrong byte.

    It is also the case that corrects "T4 means the run is refused": this function IS T4 (it
    reads the PSG at 0x17f08), yet it returns green here, because the music-playing test right
    after the tempo select exits early on the image's own initial state.
    """
    mem, writes, out = run(FN_SND_MUSIC_TICK)
    if SND_TEMPO_ADDR not in writes:
        return False, ("snd_music_tick did not write the tempo byte at %#x at all"
                       % SND_TEMPO_ADDR)
    if SND_TEMPO_MONO == SND_TEMPO_60HZ:
        return False, ("the two branches store the same tempo byte %#x, so this case cannot show "
                       "which one ran" % SND_TEMPO_MONO)
    if mem[SND_TEMPO_ADDR] != SND_TEMPO_MONO:
        return False, ("tempo byte is %#x, not the %#x the mono-monitor branch stores (the "
                       "colour/60 Hz branch would store %#x)"
                       % (mem[SND_TEMPO_ADDR], SND_TEMPO_MONO, SND_TEMPO_60HZ))
    if emu.psg_writes():
        return False, "snd_music_tick reached the PSG after all (%d writes)" % len(emu.psg_writes())
    return True, ("snd_music_tick: %d insns, tempo := %#x (the MONO-MONITOR branch, forced by a "
                  "zeroed $fffa01 bit 7) — and it returned GREEN despite being T4, because the "
                  "early exit two instructions later kept it away from the PSG"
                  % (out["ninsns"], mem[SND_TEMPO_ADDR]))


def case_t0_snd_trigger_effect():
    """T0 inside the SOUND module, whose subtree closure is exact — so "no byte of this game's
    sound is verifiable" is false. The trigger path writes the replay driver's RAM channel state
    and never touches the chip; only the tick that drains that state does. A differential over it
    needs no new harness capability at all, so the run must show BOTH halves of that: image writes
    a differential could compare, and an empty PSG ledger. The empty ledger is the half a function
    that did nothing would also produce, so entry to snd_trigger_effect itself is the control —
    the stub is 4 instructions and could "succeed" without ever reaching the routine."""
    _, writes, out, entered = run_reaching(FN_SND_TRIGGER_STUB, FN_SND_TRIGGER_EFFECT)
    written = image_writes(writes)
    if not entered:
        return False, ("the $%x stub returned without reaching snd_trigger_effect at %#x"
                       % (FN_SND_TRIGGER_STUB, FN_SND_TRIGGER_EFFECT))
    if not written:
        return False, ("snd_trigger_effect wrote no image byte, so there is nothing for a "
                       "differential to compare and the T0 claim is empty")
    if emu.psg_writes():
        return False, ("snd_trigger_effect reached the PSG (%d write(s)); it is classified as "
                       "touching no hardware at all" % len(emu.psg_writes()))
    return True, ("snd_trigger_effect (via its $%x entry stub): %d insns, %d image bytes written "
                  "over %#x..%#x, EMPTY PSG ledger — diffable today"
                  % (FN_SND_TRIGGER_STUB, out["ninsns"], len(written), min(written), max(written)))


def case_t0_bg_scroll_copy():
    """T0, and the second unrolled blit family — the one that sat in NO tier until it was named.

    Variant 0 with d7 = d6 = 0 runs both halves once each: 120 bytes from `a0`, then 120 more from
    `a0 + 8 - BG_SCROLL_SRC_WRAP` after the `lea -$5800(a0),a0` rewind, landing one 160-byte
    scanline lower. BOTH source rows are seeded with DIFFERENT patterns and both destinations are
    checked: the scratch area is zero in a fresh image, so seeding only the first row leaves the
    second copying zeroes into zeroes — which is also what a wrong rewind constant, or no copy at
    all, produces. (Mutating the rewind to -22000 passes without the second pattern and fails with
    it.)"""
    image = bytearray(IMAGE)
    first = bytes((i * 7 + 1) & 0xFF for i in range(BG_SCROLL_BYTES_PER_ROW))
    second = bytes((i * 11 + 3) & 0xFF for i in range(BG_SCROLL_BYTES_PER_ROW))
    second_src = SCRATCH_SRC + BG_SCROLL_SRC_ROW_STRIDE - BG_SCROLL_SRC_WRAP
    image[SCRATCH_SRC:SCRATCH_SRC + len(first)] = first
    image[second_src:second_src + len(second)] = second
    mem, writes, out = run(FN_BG_SCROLL_COPY_X0, image=image,
                           regs={"a0": SCRATCH_SRC, "a1": SCRATCH_DST, "d6": 0, "d7": 0})
    written = image_writes(writes)
    second_dst = SCRATCH_DST + BG_SCROLL_DEST_STRIDE
    expected = set(range(SCRATCH_DST, SCRATCH_DST + BG_SCROLL_BYTES_PER_ROW))
    expected |= {a + BG_SCROLL_DEST_STRIDE for a in expected}
    if written != expected:
        return False, ("bg_scroll_copy_x0 wrote %d image byte(s), expected the two %d-byte rows "
                       "%d bytes apart that its two halves copy"
                       % (len(written), BG_SCROLL_BYTES_PER_ROW, BG_SCROLL_DEST_STRIDE))
    if mem[SCRATCH_DST:SCRATCH_DST + len(first)] != first:
        return False, "bg_scroll_copy_x0's first half wrote the right addresses but not its source"
    if mem[second_dst:second_dst + len(second)] != second:
        return False, ("bg_scroll_copy_x0's second half did not copy the row at %#x, i.e. it did "
                       "not rewind a0 by %#x" % (second_src, BG_SCROLL_SRC_WRAP))
    return True, ("bg_scroll_copy_x0: %d insns, copied both seeded %d-byte rows — the second from "
                  "%#x, %#x below the first, which is the source buffer's vertical wrap"
                  % (out["ninsns"], BG_SCROLL_BYTES_PER_ROW, second_src, BG_SCROLL_SRC_WRAP))


def case_bg_scroll_table_matches_names():
    """Pin all 16 background-scroll names to the table the game dispatches through.

    Only variant 0 is executed above, and Ghidra builds no call edge through a `jmp (a2)` — so
    without this, 15 of the 16 `fn` lines rest on a hand-read table and a mis-transcribed address
    would survive a re-bootstrap while still being counted as a measured, T0, "start here"
    function. names.txt is the source of truth (CLAUDE.md), so the IMAGE is checked against it.
    """
    table = struct.unpack(">%dI" % BG_SCROLL_VARIANTS,
                          IMAGE[BG_SCROLL_TABLE_ADDR:BG_SCROLL_TABLE_ADDR + 4 * BG_SCROLL_VARIANTS])
    named = {}
    for line in CONFIG.names.read_text().splitlines():
        f = line.split()
        if len(f) >= 3 and f[0] == "fn" and f[2].startswith(BG_SCROLL_NAME_PREFIX):
            named[int(f[2][len(BG_SCROLL_NAME_PREFIX):])] = int(f[1], 16)
    if len(named) != BG_SCROLL_VARIANTS:
        return False, ("names.txt has %d `%s*` functions, not the %d entries of the table at %#x"
                       % (len(named), BG_SCROLL_NAME_PREFIX, BG_SCROLL_VARIANTS,
                          BG_SCROLL_TABLE_ADDR))
    wrong = [i for i in range(BG_SCROLL_VARIANTS) if named[i] != table[i]]
    if wrong:
        return False, ("%s%d is named %#x but the table at %#x dispatches to %#x"
                       % (BG_SCROLL_NAME_PREFIX, wrong[0], named[wrong[0]], BG_SCROLL_TABLE_ADDR,
                          table[wrong[0]]))
    return True, ("bg_scroll_blit_table: all %d entries at %#x equal the `%s*` addresses in "
                  "names.txt, in order" % (BG_SCROLL_VARIANTS, BG_SCROLL_TABLE_ADDR,
                                           BG_SCROLL_NAME_PREFIX))


CASES = [
    ("map", case_bg_scroll_table_matches_names),
    ("T0", case_t0_copy_longs),
    ("T0", case_t0_bg_scroll_copy),
    ("T0", case_t0_snd_trigger_effect),
    ("T2", case_t2_video_set_lowres),
    ("T2", case_t2_clear_palette),
    ("T3", case_t3_fdc_wait_irq),
    ("T3", case_t3_fdc_restore),
    ("T3", case_t3_fdc_read_address_command),
    ("T3", case_t3_fdc_read_sector_command),
    ("T3", case_t3_ikbd_disable_mouse),
    ("T4", case_t4_psg_set_drive_select),
    ("T4", case_t4_sound_psg_read),
    ("T3", case_t3_music_tempo_is_chosen_by_a_zeroed_read),
]


def main():
    failures = 0
    for tier, case in CASES:
        try:
            ok, detail = case()
        except Exception as err:                                  # noqa: BLE001
            ok, detail = False, "%s: %s" % (type(err).__name__, err)
        failures += not ok
        print("%-4s %-4s %s" % (tier, "ok" if ok else "FAIL", detail))
    print("\n%d case(s), %d failure(s)" % (len(CASES), failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
