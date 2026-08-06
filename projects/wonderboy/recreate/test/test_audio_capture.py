"""Pin the kit's opt-in AUDIO-CAPTURE mode (`emu.audio_capture`) — both halves of what it promises.

A kit behaviour tested in a game's suite, for the same reason `test_poked_input_guard.py` is: the
kit's own `make test` binds no project, so it has no 68000 code to run the mode against. Wonder Boy
is the game the mode was built for — its replayer holds both of the PSG read-backs (`snd_psg_silence`
at `$17f30`, reading at `$17f3e`; `snd_music_tick` at `$17c74`, reading at `$17f08`) and the two-byte
tempo selector the mode answers — so it is where the wiring can be exercised at all.
`../notes/sound_module_recon.md` has the full module.

WHAT THE MODE IS, SINCE THE SEEDED READ MODEL LANDED (`tools/recreate_kit/TRAP_MODEL.md`, Phase 6).
The `$ff8800` read-back is no longer the mode's own invention: the differential models it too, from
a register file the CASE seeds, and refuses only a register nothing declared and nothing wrote. The
mode is a documented RELAXATION of that one model over that one register file — not a second model —
and its contract is two claims, both load-bearing:

  * ON, an undeclared register reads **0** instead of refusing, the register file and the select
    latch SPAN runs instead of being re-seeded per run, and the 50 Hz colour-ST tempo bytes on
    `$fffa01` bit 7 / `$ff820a` bit 1 are served. Without the first an extraction tool cannot run the
    replayer at all — it cannot declare a seed per tick, so the first mixer read-back sinks the run —
    and without the tempo bytes it would run it WRONG and silently: 0/0 there is the MONOCHROME
    profile, which drops 72/256 of all ticks.
  * OFF — the default, and every other test in this suite — none of that applies. That is not a
    nicety: each relaxation is the model's invention rather than the game's data, so a reconstruction
    "verified" under one would be verified against `shim.c`. The refusal is the differential's whole
    point, so the cases below check that it is intact by default AND that it comes back when the mode
    is switched off, rather than only that the mode works when on.

The register file and the select latch surviving `run()` are the third thing pinned here, because
they are the property an extractor rests on and the one a per-run reset would break invisibly: it
calls `run()` once per VBL tick, and tick N's read-modify-write must read what tick N-1 wrote.

Every case scopes the mode with `emu.audio_capturing()`, which arms + clears on entry and disarms on
exit however the block leaves. That is what keeps the mode from leaking: it is PROCESS-global state
in the shared oracle, `make test` runs `-n auto`, and a case that left it armed would change later
cases in the same worker — WHICH ones not even being stable between runs.

WHAT IS NOT PINNED HERE: `snd_music_tick`'s own read-back at `$17f08`. Reaching it needs a song
loaded and the engine enabled (the tick bails at `$17ca0` otherwise), which is the extractor's job,
not this file's — `snd_stop` reaches the identical register-file model in four instructions.
"""
import pytest

import harness  # noqa: F401  — binds the kit; the imports below only work afterwards
import emu
import leaf
import loader

# snd_psg_silence's PSG traffic: `select reg 7 / read it back / ori.b #$3f / write it back`, then
# the three volume registers zeroed. MIXER_ALL_OFF is the mask it ORs in — all six tone+noise bits.
PSG_MIXER_REG = 7
MIXER_ALL_OFF = 0x3f
PSG_VOLUME_REGS = (8, 9, 10)
PSG_SILENCE_VOLUME_WRITES = [(reg, 0) for reg in PSG_VOLUME_REGS]

# Mixer bits 6 and 7 are the PSG's port A/B I/O DIRECTION bits, which `ori.b #$3f` does not touch —
# so they are exactly what the read-back exists to preserve, and what a fabricated 0 would destroy
# (port A carries the floppy drive-select lines psg_set_drive_select drives). Seeding them is how a
# case tells a real read-back apart from a zero one: $3f alone is what BOTH produce.
PSG_PORT_DIR_BITS = 0xc0

# What the tempo selector writes at `snd_tick_drop_value`, per ../notes/sound_module_recon.md §4:
# the fraction of ticks dropped, out of 256. The mono value is what unmodeled (0-returning) hardware
# reads select, and it is 28% of every tick silently discarded.
TEMPO_SKIP_50HZ_COLOUR = 0x00
TEMPO_SKIP_MONO = 0x48

# The chip's register-select latch (shim.c's `#define PSG_SELECT`). Its odd alias is +1 and the data
# port +2, spelled as offsets from this one address rather than as literals of their own so that the
# three cannot drift apart.
PSG_SELECT = 0xff8800
# The shifter's sync-mode byte (shim.c's `#define SHIFTER_SYNC`), half of the tempo pair.
SHIFTER_SYNC = 0xff820a

# The data register every snippet below reads a port into; `emu.run` reports it back by name.
READ_BACK_REG = 1
READ_BACK_NAME = f"d{READ_BACK_REG}"
BYTE_MASK = 0xff

# Direct PSG accesses OUTSIDE the modeled byte read-back, which the mode does not widen: a word-wide
# read of the select port; a byte read of the odd alias $ff8801 (the ST decodes the chip
# incompletely, so the alias answers on real hardware — its decoding is simply not modeled); and a
# byte read of the DATA port $ff8802, which on a real ST is write-only — the chip reads back through
# the select port, so answering $ff8802 would invent a port the hardware does not have.
UNMODELED_PSG_READS = {
    "word_wide": leaf.move_w_abs_l_dn(READ_BACK_REG, PSG_SELECT) + leaf.RTS,
    "odd_alias": leaf.move_b_abs_l_dn(READ_BACK_REG, PSG_SELECT + 1) + leaf.RTS,
    "data_port": leaf.move_b_abs_l_dn(READ_BACK_REG, PSG_SELECT + 2) + leaf.RTS,
}

SNIPPET_INSN_CAP = 16           # any snippet here is a handful of instructions; a runaway is a bug
PSG_REFUSAL = "accessed the PSG ports"      # emu.run's cause for a PSG read it cannot serve
PROFILE_REFUSAL = "machine-profile bytes"   # ...and for a non-byte read of the tempo pair


def _run_snippet(code):
    """Run a hand-assembled snippet from the image's load base. Returns ``emu.run``'s triple."""
    return emu.run(harness.make_image({loader.LOAD_BASE: code}), loader.LOAD_BASE,
                   max_insns=SNIPPET_INSN_CAP)


def _seed_mixer_register(value):
    """A synthetic replayer tick: select mixer register 7 and write ``value`` to it.

    The shortest thing that puts a known byte into the modeled register file, so a later run can
    prove a read-back returned THAT byte rather than a plausible zero.
    """
    _run_snippet(leaf.move_b_imm_abs_l(PSG_MIXER_REG, PSG_SELECT)
                 + leaf.move_b_imm_abs_l(value, PSG_SELECT + 2) + leaf.RTS)
    assert emu.psg_writes() == [(PSG_MIXER_REG, value)], "the seed run itself misfired"


def _assert_snd_stop_writes(expected_mixer):
    """Run the original `snd_stop` on a pristine image and state its whole PSG stream.

    The mixer value is what the case is really about — it is `ori.b #$3f` applied to whatever the
    read-back returned — but the volume writes are asserted alongside it so that a mode which
    silently changed what `psg_writes()` reports would fail here too.
    """
    emu.run(harness.make_image(), leaf.entry_of("snd_stop"))
    assert emu.psg_writes() == [(PSG_MIXER_REG, expected_mixer)] + PSG_SILENCE_VOLUME_WRITES


def test_the_mixer_read_back_is_refused_when_the_mode_is_off():
    """The default, and the differential's contract: `snd_stop` cannot be run AS THIS CASE IS WRITTEN.

    Its `move.b $ff8800,d1` at `$17f3e` reads mixer register 7, and nothing here declares what the
    chip held there — no `psg_seed`, and no earlier write in the run — so the model refuses rather
    than invent it, and serving 0 would let a reconstruction of the read-modify-write be "verified"
    against a value shim.c fabricated. The remedy off the mode is `psg_seed={7: <byte>}`, which is
    what a differential of that routine will use; what this case pins is that the refusal is the
    DEFAULT. The cause is matched, not merely `RuntimeError`, so a run that fails for an unrelated
    reason cannot pass this case.
    """
    with pytest.raises(RuntimeError, match=PSG_REFUSAL):
        emu.run(harness.make_image(), leaf.entry_of("snd_stop"))


def test_the_mode_serves_the_mixer_read_back_from_the_register_file():
    """ON, the same run completes and its whole PSG stream is captured.

    From a freshly cleared register file the read-back is 0 — the mode's relaxation — so `ori.b #$3f`
    yields $3f, which is why this case cannot tell a real read-back from a fabricated zero and why
    the seeded case below exists. What it does pin is that the run is no longer refused and
    `psg_writes()` — the extractor's data feed, the WRITE projection of the access ledger — still
    reports every write and only writes, unchanged by the mode.
    """
    with emu.audio_capturing():
        _assert_snd_stop_writes(MIXER_ALL_OFF)
        assert emu.psg_file()[PSG_MIXER_REG] == MIXER_ALL_OFF


def test_the_read_back_keeps_the_bits_the_register_file_holds_across_runs():
    """The case that distinguishes a modeled read-back from a fabricated 0 — and the one an
    extractor rests on, since it also pins the file PERSISTING from one `run()` to the next.

    Two separate runs, exactly as a per-VBL extractor issues them: the first writes $c0 (the port
    A/B direction bits) into mixer register 7, the second is `snd_stop`, whose `ori.b #$3f` must see
    that $c0 and write $ff back. A per-run reset — or a read served as 0 — gives $3f here, clearing
    the direction bits and floating the floppy drive-select lines on real hardware.
    """
    with emu.audio_capturing():
        _seed_mixer_register(PSG_PORT_DIR_BITS)
        _assert_snd_stop_writes(PSG_PORT_DIR_BITS | MIXER_ALL_OFF)


def test_the_select_latch_survives_a_run_in_capture_mode():
    """The other half of "the capture spans runs": the SELECT LATCH persists too.

    A tick that reads a register back without re-selecting it — the chip's latch survives a VBL, so
    a replayer is entitled to assume it — must see the register the previous tick selected. The
    second run here executes nothing but `move.b $ff8800,d1`, so a per-run latch reset would answer
    from register 0 and hand back its (zero) contents instead of the $c0 in register 7.
    """
    with emu.audio_capturing():
        _seed_mixer_register(PSG_PORT_DIR_BITS)
        _, _, out_regs = _run_snippet(leaf.move_b_abs_l_dn(READ_BACK_REG, PSG_SELECT) + leaf.RTS)
    assert out_regs[READ_BACK_NAME] & BYTE_MASK == PSG_PORT_DIR_BITS


def test_audio_reset_clears_the_register_file():
    """Where a new capture begins. Mid-capture the file survives every `run()` AND every re-arm, so
    `audio_reset` is the only point at which "forget the previous capture" can be expressed — an
    extractor that reloads a pristine image between songs would otherwise carry the last song's mixer
    into the next. (Arming from OFF clears it too, since the file is shared with the differential's
    seeded model; that half is pinned kit-side, in tools/recreate_kit/test/test_psg_model.py.)
    """
    with emu.audio_capturing():
        _seed_mixer_register(PSG_PORT_DIR_BITS)
        assert emu.psg_file()[PSG_MIXER_REG] == PSG_PORT_DIR_BITS

        emu.audio_reset()
        assert emu.psg_file() == bytes(emu.PSG_NREGS)


def test_re_arming_the_mode_leaves_the_register_file_alone():
    """Arming is IDEMPOTENT — it is a toggle, not a reset (the `cov_enable`/`cov_reset` shape).

    An extractor that arms defensively before each tick, or a caller that nests the mode, would
    otherwise silently wipe the capture it is in the middle of; the read-back would then answer 0 and
    the songs would come out subtly wrong rather than loudly missing. Fused enable-and-clear is what
    this case exists to catch, so the file is seeded first and compared whole.
    """
    with emu.audio_capturing():
        _seed_mixer_register(PSG_PORT_DIR_BITS)
        seeded = emu.psg_file()
        assert seeded != bytes(emu.PSG_NREGS), "nothing was seeded, so re-arming cannot lose it"

        emu.audio_capture(True)
        assert emu.psg_file() == seeded


def test_the_mode_reports_the_50hz_colour_machine_profile():
    """`snd_music_tick`'s tempo selector, which is not a PSG access at all and so is green either
    way — it is the mode's other half, and the one that fails SILENTLY without it.

    Unmodeled hardware reads return 0; bit 7 of `$fffa01` clear means "monochrome monitor", so the
    replayer installs the mono tick-drop value and a capture ticked at 50 Hz renders every song 28%
    slow with nothing raising. Both readings are asserted, so the case fails if the mode stops
    serving the profile AND if it ever starts serving it by default.
    """
    tick = leaf.entry_of("snd_music_tick")
    tempo = leaf.entry_of("snd_tick_drop_value")

    off, _, _ = emu.run(harness.make_image(), tick)
    assert off[tempo] == TEMPO_SKIP_MONO

    with emu.audio_capturing():
        on, _, _ = emu.run(harness.make_image(), tick)
    assert on[tempo] == TEMPO_SKIP_50HZ_COLOUR


def test_switching_the_mode_off_restores_the_refusal():
    """The mode is a mode, not a one-way door: a process that captured audio must be able to go back
    to running differentials, and the refusal is what a differential's honesty rests on.
    """
    with emu.audio_capturing():
        assert emu.audio_capture_on(), "the mode never armed, so switching it off proves nothing"

    with pytest.raises(RuntimeError, match=PSG_REFUSAL):
        emu.run(harness.make_image(), leaf.entry_of("snd_stop"))


@pytest.mark.parametrize("what", sorted(UNMODELED_PSG_READS))
def test_a_psg_read_outside_the_byte_protocol_is_still_refused_in_capture_mode(what):
    """Only ONE read of the chip is modeled at all — a byte read of the canonical select port — and
    the mode widens nothing. A word-wide access, the odd alias `$ff8801` and the write-only data port
    `$ff8802` all depend on decoding the model does not have, so answering them would be fabrication
    of a kind the mode's relaxations are careful not to be: those relax what a KNOWN read answers,
    never which accesses exist.
    """
    with emu.audio_capturing():
        with pytest.raises(RuntimeError, match=PSG_REFUSAL):
            _run_snippet(UNMODELED_PSG_READS[what])


def test_a_differential_is_refused_while_the_mode_is_armed():
    """The enforcement half of "never valid for a differential" (`harness._vet_audio_capture_off`).

    Armed, the oracle answers reads that `shim.c` invented, so a clean diff would say the candidate
    agrees with the SHIM rather than with the original. The mode is process-global, so nothing about
    a case says whether it is armed — an extractor in the same process, or a block that raised on its
    way out, is enough — which is why this is a vet rather than a convention. It fires before
    anything runs, so the glue below is never called.
    """
    with emu.audio_capturing():
        with pytest.raises(AssertionError, match="AUDIO-CAPTURE mode is armed"):
            harness.differential(leaf.entry_of("snd_stop"), {}, lambda _lib, _image: None)


def test_a_wide_read_of_a_machine_profile_byte_is_refused_in_capture_mode():
    """The tempo bytes are served as BYTES and only as bytes.

    `move.w $ff820a,d1` takes in the shifter register next door, which the model knows nothing about
    and would have to fabricate as 0 — the mode answers two named bits, not a machine. Off the mode
    this same read is an ordinary off-image read answered 0 (the T3 tier in
    `../PORTABILITY.md`), so the refusal is the mode's own and has to be pinned under it.
    """
    with emu.audio_capturing():
        with pytest.raises(RuntimeError, match=PROFILE_REFUSAL):
            _run_snippet(leaf.move_w_abs_l_dn(READ_BACK_REG, SHIFTER_SYNC) + leaf.RTS)
