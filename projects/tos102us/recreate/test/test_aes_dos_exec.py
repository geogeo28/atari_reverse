"""dos_exec `$fe3d2e` (`src/aes/gemdosif.c`, and `gemdosif.S` on target): Pexec, with the running process's saved
supervisor SP moved under its caller's frames while the program runs — hand 68000, `trap #1` taken by itself.

    dos_exec(name, mode.w, tail):
        spl7;  $8c2e = UDA.super_sp;  UDA.super_sp = SP - 64;  splx          (UDA: rlr's, read through $c794)
        D0 = Pexec(mode, name, tail, 0)
        spl7;  UDA.super_sp = $8c2e;  splx                                   (UDA read through $c794 AGAIN)
        $98ec = 0;  if (D0.w != 0) { $98ec = 1;  $c918 = D0.w }
        return D0

WHY THE PARK. A program dos_exec starts makes its AES calls by `trap #2`, and the trap's handler takes the process's
stack from its UDA's saved supervisor SP: left where the caller's last dispatch parked it, the program's calls would
stack OVER the frames of the caller that is waiting for it. So the SP is put 64 bytes under dos_exec's own.

EVERY CASE OVER A RECORDING, SCRIPTED TRAP OF ITS OWN (`aes_gemdosif.EXEC`): Pexec's whole frame — the mode, the
name, the tail and the environment — and WHAT THE UDA'S SP AND `$8c2e` HOLD AT THE TRAP, which nothing shows once
dos_exec has returned (it puts the SP back). No program is run: a LABELLED ARGUMENT CLASS, the scripted answers
standing for a program that ended and for a basepage (mode 5).

A REAL LAUNCH IS NOT HELD, AND IS NOT DESIGNED: `Pexec(0)` loads the program into the largest free block, which is
where the harness lays the blob and its stack (band 5 wave 3's design, §7.9). What reaches dos_exec on a booted
machine — sh_main after the desk returns a launch, the cartridge's two roads — is reached by no boot today.

THE VERDICT IS dos_exec'S OWN, NOT `__DOS`'S: the answer's WORD against 0, where `__DOS` reads the LONG's sign. So a
mode-5 basepage whose address has a non-zero low word — every real one — reads as a failure (`$98ec` 1, `$c918` the
address's low word), and a negative long whose low word is 0 reads as a success. The ROM's; reproduced.
"""
import pytest

from harness import BASE_IMAGE, addrs, bench_tier3, emu, make_image
from recreate_kit import rom_bench

import aes
import aes_gemdosif as gd
import aes_shell as shell
import case
import gemdos
import test_aes_gsx_transcription as frames
import transcription
import vdi
from case import merge_pokes

DOS_EXEC = "AES_ROM_DOS_EXEC"
# The C twin is handed the SP dos_exec is entered with — the machine's, carried by no frame: a host argument.
aes.declare_alcyon(DOS_EXEC, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.LONG_ARG, vdi.WORD_ARG, vdi.LONG_ARG),
                   host_arguments=1)
GEMDOSIF = aes.header_constants("gemdosif.h")
STACK_KEPT = GEMDOSIF["DOS_EXEC_STACK_KEPT"]
SAVED_SSP = gd.DOS_EXEC_SAVED_SSP
UDA_SUPER_SP = gd.SHELL_UDA_SUPER_SP
ARGUMENT_CLASS = "ARGUMENT CLASS (Pexec scripted: no program runs)"
PEXEC = gd.PEXEC
PEXEC_LOAD_GO, PEXEC_BASEPAGE, PEXEC_GO = 0, 5, 4      # Pexec's modes the ROM's callers hand dos_exec ($feb2a2 `clr.w`; $fed586, $fed5f0 `#5`; $fed608 `#4`)
NAME_AT = gd.PATH_AT
TAIL_AT = aes.RECTS_AT
NAME = merge_pokes(shell.text(NAME_AT, "A:\\PROGRAM.PRG", gd.PATH_BYTES))
TAIL = {TAIL_AT: b"\x05HELLO\0"}
ENDED_WELL, EFILNF, ENSMEM = 0, -33, -39
A_BASEPAGE = gd.BASEPAGE_AT
STALE_SAVED = {SAVED_SSP: vdi.STALE_LONG.to_bytes(aes.LONG_BYTES, "big")}
aes.declare_case_field(SAVED_SSP, aes.LONG_BYTES, "dos_exec's save of the UDA's supervisor SP")
# THE SP dos_exec IS ENTERED WITH, on both of the harness's roads: the run's stack top, its return address there (a
# direct entry pushes the sentinel; the Line-F caller drops that longword before its call word pushes its own).
ENTRY_SP = emu.STACK_TOP
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))


def hook():
    return gemdos.bound_handlers(gd.EXEC_HANDLERS)


@pytest.fixture(scope="module")
def sr_parked():
    """What the mask bracket parks in AES_SR_SPL on the ROM's run — the status register the harness runs under, which
    the host's bracket cannot store: staged, so the word is compared and found as the ROM leaves it."""
    final, _writes, _regs = emu.run(make_image(aes.staged(DOS_EXEC, (0, 0, 0), machine([0]))), addrs.AES_ROM_DOS_EXEC, {})
    return {aes.AES_SR_SPL: bytes(final[aes.AES_SR_SPL:aes.AES_SR_SPL + aes.WORD_BYTES])}


def machine(answers, pokes=None, running=aes.SHELL_PD):
    """The leaf machine over dos_exec's recorder, `$8c2e` and the glue's verdict stale — the shell's PD running, or
    (an ARGUMENT CLASS) `running`, laid over the leaf machine's own lever."""
    leaf = aes.leaf_machine(onto=merge_pokes(gd.STALE_DOS, STALE_SAVED, NAME, TAIL, gd.EXEC.pokes(answers), pokes))
    return merge_pokes(leaf, aes.field_pokes("AES", RLR=running))


def dos_exec(answer, sr_parked, *, mode=PEXEC_LOAD_GO, name=NAME_AT, tail=TAIL_AT, running=aes.SHELL_PD, **kwargs):
    return aes.run_function(DOS_EXEC, (name, mode, tail), machine([answer], sr_parked, running), hook=hook,
                            poison=False, host_arguments=(ENTRY_SP,), **kwargs)


def pexec(mode=PEXEC_LOAD_GO, name=NAME_AT, tail=TAIL_AT):
    return gd.EXEC.call(PEXEC, ("w", mode), ("l", name), ("l", tail), ("l", 0))


def verdict(result):
    return result.field("AES", "DOS_ERR"), result.field("AES", "DOS_AX")


STALE_VERDICT = tuple(case.word_in(make_image(gd.STALE_DOS), at) for at in (aes.AES_DOS_ERR, aes.AES_DOS_AX))
THE_DESK_S_SSP = case.long_in(BASE_IMAGE, UDA_SUPER_SP)
THE_MANAGER_S = case.long_in(BASE_IMAGE, aes.SCREEN_MANAGER_PD + aes.PD_UDA) + gd.UDA_SUPER_SP     # its UDA's saved SP


# ---- the park ------------------------------------------------------------------------------------------------------------
@THROUGH
@pytest.mark.parametrize("mode", (PEXEC_LOAD_GO, PEXEC_BASEPAGE, PEXEC_GO), ids=("load and go", "a basepage", "go"))
def test_pexec_is_taken_with_the_uda_s_sp_parked_under_dos_exec_s_own_and_the_sp_put_back(mode, through_line_f, sr_parked):
    """ONE Pexec: the caller's mode, name and tail, NO environment. AT THE TRAP the UDA's supervisor SP stands 64
    bytes under the SP dos_exec was entered with and `$8c2e` holds the one it displaced; where dos_exec returns the
    UDA holds that one again (and `$8c2e` still does)."""
    result = dos_exec(ENDED_WELL, sr_parked, mode=mode, through_line_f=through_line_f)
    assert gd.EXEC.calls(result.final) == [pexec(mode)]
    assert gd.EXEC.parked_at(result.final) == [(ENTRY_SP - STACK_KEPT, THE_DESK_S_SSP)]
    assert (result.long(UDA_SUPER_SP), result.long(SAVED_SSP)) == (THE_DESK_S_SSP, THE_DESK_S_SSP)
    assert result.long_answer() == ENDED_WELL


def test_the_sp_parked_is_the_rom_s_own_sp_at_entry_less_64():
    """THE HOST ARGUMENT, held to the machine: the ROM's own run stopped at its first instruction has SP where the
    twin is told it is, on both of the harness's roads (the second: a run entered at the Line-F caller)."""
    staged = aes.staged(DOS_EXEC, (NAME_AT, PEXEC_LOAD_GO, TAIL_AT), machine([ENDED_WELL]))
    final, _writes, _regs = emu.run(make_image(staged), addrs.AES_ROM_DOS_EXEC, {})
    assert gd.EXEC.parked_at(final) == [(emu.STACK_TOP - STACK_KEPT, THE_DESK_S_SSP)]


def test_the_uda_is_the_running_process_s_read_through_rlr_on_both_sides_of_the_trap():
    """ARGUMENT CLASS (the screen manager's PD running): the SP parked and put back is THAT process's UDA's, and the
    shell's is left alone. `rlr` is read again after the trap ($fe3d7e) — the same process here."""
    pokes = machine([ENDED_WELL], running=aes.SCREEN_MANAGER_PD)
    final, writes, _regs = emu.run(make_image(aes.staged(DOS_EXEC, (NAME_AT, PEXEC_LOAD_GO, TAIL_AT), pokes)),
                                   addrs.AES_ROM_DOS_EXEC, {})
    assert {THE_MANAGER_S + byte for byte in range(aes.LONG_BYTES)} <= set(writes)
    assert not set(writes) & {UDA_SUPER_SP + byte for byte in range(aes.LONG_BYTES)}
    assert case.long_in(final, SAVED_SSP) == case.long_in(BASE_IMAGE, THE_MANAGER_S) == case.long_in(final, THE_MANAGER_S)


def test_the_twin_parks_the_running_process_s_too(sr_parked):
    """...and the C over the same machine: the differential, and the recorder — which reads the SHELL's UDA — finds
    that one unparked at the trap while `$8c2e` holds the screen manager's."""
    result = dos_exec(ENDED_WELL, sr_parked, running=aes.SCREEN_MANAGER_PD)
    assert gd.EXEC.parked_at(result.final) == [(THE_DESK_S_SSP, case.long_in(BASE_IMAGE, THE_MANAGER_S))]
    assert result.long(THE_MANAGER_S) == case.long_in(BASE_IMAGE, THE_MANAGER_S)


# ---- the verdict ---------------------------------------------------------------------------------------------------------
# (Pexec's answer, AES_DOS_ERR, AES_DOS_AX — None: left as found)
ANSWERS = {
    "the program ended with 0": (ENDED_WELL, 0, None),
    "the program ended with 1": (1, 1, 1),
    "file not found": (EFILNF, 1, EFILNF & aes.WORD_MASK),
    "no memory": (ENSMEM, 1, ENSMEM & aes.WORD_MASK),
    "a basepage (mode 5): its low word is not 0, so it reads as an error": (A_BASEPAGE, 1, A_BASEPAGE & aes.WORD_MASK),
    "a positive long whose low word is 0: no error": (0x0002_0000, 0, None),
    "A NEGATIVE long whose low word is 0: no error either": (0x8000_0000, 0, None),
}


@THROUGH
@pytest.mark.parametrize("answered", ANSWERS)
def test_the_verdict_is_the_answer_s_word_against_0(answered, through_line_f, sr_parked):
    """`$98ec` cleared; set — with `$c918` the answer's word — only where THE WORD is not 0. D0 the trap's whole long."""
    answer, failed, ax = ANSWERS[answered]
    result = dos_exec(answer, sr_parked, mode=PEXEC_BASEPAGE if "basepage" in answered else PEXEC_LOAD_GO,
                      through_line_f=through_line_f)
    assert result.long_answer() == answer & aes.LONG_MASK
    assert verdict(result) == (failed, STALE_VERDICT[1] if ax is None else ax)
    assert result.long(UDA_SUPER_SP) == THE_DESK_S_SSP, "the SP is put back whatever Pexec answered"


def test_the_pointers_and_the_mode_are_handed_on_as_given(sr_parked):
    """The name and the tail reach GEMDOS top byte and all, the mode's whole word."""
    name, tail, mode = NAME_AT | aes.BUS_TAG, TAIL_AT | aes.BUS_TAG, 0x1205
    assert gd.EXEC.calls(dos_exec(ENDED_WELL, sr_parked, mode=mode, name=name, tail=tail).final) == [pexec(mode, name, tail)]


# ---- who calls it ---------------------------------------------------------------------------------------------------------
# The ROM's four Line-F calls, each with the mode it hands: sh_main's launch, the cartridge's accessories, and
# cart_exec's pair (a basepage, then go).
ROM_CALLS = {0xFEB2AA: PEXEC_LOAD_GO, 0xFED590: PEXEC_BASEPAGE, 0xFED5FA: PEXEC_BASEPAGE, 0xFED612: PEXEC_GO}
CLR_W_PUSHED, MOVE_W_IMMEDIATE_PUSHED = 0x4267, 0x3F3C
A_LONG_PUSH_BYTES = 6                   # `move.l <abs>.l,-(sp)` / `move.l #<imm>,-(sp)`: the name, pushed last


def mode_pushed_before(call):
    """The mode the caller of the Line-F call at `call` pushes: the instruction before the name's — `clr.w -(sp)`,
    or `move.w #mode,-(sp)`."""
    name_pushed_at = call - A_LONG_PUSH_BYTES
    if case.word_in(BASE_IMAGE, name_pushed_at - aes.WORD_BYTES) == CLR_W_PUSHED:
        return 0
    assert case.word_in(BASE_IMAGE, name_pushed_at - 2 * aes.WORD_BYTES) == MOVE_W_IMMEDIATE_PUSHED, f"${call:x}"
    return case.word_in(BASE_IMAGE, name_pushed_at - aes.WORD_BYTES)


def test_the_rom_s_four_callers_hand_it_the_three_modes_the_cases_run():
    """WHAT REACHES IT (none of them by any boot today): every Line-F call of dos_exec in the GEM text, and the mode
    each pushes — the three the battery runs. NO C CALLS IT YET (sh_main is wave 4's, the cartridge's roads are not
    in this wave): its first caller's pair goes into `transcription.C_CALLERS_OF_TRANSCRIBED_CORES`."""
    assert sorted(at for sites in aes.line_f_call_sites(DOS_EXEC).values() for at in sites) == sorted(ROM_CALLS)
    assert {call: mode_pushed_before(call) for call in ROM_CALLS} == ROM_CALLS
    assert not [caller for caller, core in transcription.C_CALLERS_OF_TRANSCRIBED_CORES if core == "aes_dos_exec"]


def test_the_twin_s_trap_is_the_recorder_s_own_handler():
    """The handler under the ROM's own dos_exec: what it records and answers is the handler's, not a claim of the C."""
    final, _writes, regs = emu.run(make_image(aes.staged(DOS_EXEC, (NAME_AT, PEXEC_GO, TAIL_AT), machine([0x1234_5678]))),
                                   addrs.AES_ROM_DOS_EXEC, {})
    assert gd.EXEC.calls(final) == [pexec(PEXEC_GO)] and regs["d0"] == 0x1234_5678


# ---- THE `.S`: what the target ships ---------------------------------------------------------------------------------------
# Held to the ROM through Tier 3's transcription relation — the whole image, the whole register file, NOTHING DROPPED
# and nothing mapped: dos_exec leaves no address of its own text in compared memory (its three return addresses are
# pushed on the run's own stack, below where it returns).
S_ENTRY = transcription.transcription_symbol(DOS_EXEC)
S_ARGUMENTS = (NAME_AT, PEXEC_LOAD_GO, TAIL_AT)
S_ROWS = {
    f"{ARGUMENT_CLASS}: the program ended with 0": (S_ARGUMENTS, ENDED_WELL),
    f"{ARGUMENT_CLASS}: the program ended with 1": (S_ARGUMENTS, 1),
    f"{ARGUMENT_CLASS}: Pexec refuses (file not found)": (S_ARGUMENTS, EFILNF),
    f"{ARGUMENT_CLASS}: a basepage (mode 5)": ((NAME_AT, PEXEC_BASEPAGE, TAIL_AT), A_BASEPAGE),
    f"{ARGUMENT_CLASS}: a negative long whose low word is 0": (S_ARGUMENTS, 0x8000_0000),
}
for _label, (_arguments, _answer) in S_ROWS.items():
    frames.register(_label, DOS_EXEC, _arguments, machine([_answer]))


def _s_row(label):
    return bench_tier3().row_named((S_ENTRY, label))


@pytest.mark.parametrize("label", S_ROWS)
def test_the_transcription_behaves_as_the_rom(label, blob):
    """Both blobs hold the one `.S`: the image whole — the ledger with the park in it, the UDA, `$8c2e`, the verdict,
    the status register the brackets park — and the register file whole."""
    bench_tier3()._measure_transcription(_s_row(label), blob)


@pytest.mark.parametrize("label", S_ROWS)
def test_what_the_transcription_parks_is_the_rom_s_own_park_and_it_puts_the_sp_back(label, blob):
    """...AND WHAT IT STANDS ON, read off OUR run alone (the kit's own `_call`, nothing compared for it): the Pexec
    made is the case's; AT THE TRAP the UDA's SP is the very address the ROM's own run of the row parks — under the
    frame caller's pushes, 64 bytes under the SP both are entered with — and no longer the one it displaced, which
    `$8c2e` holds; where the run ends the UDA holds the displaced one again."""
    row, (arguments, answer) = _s_row(label), S_ROWS[label]
    regs = [row.regs[name] for name in emu.REPORTED_REGS]
    ours = rom_bench.RomBench._call(blob, make_image(row.pokes), row.symbol, args=(blob.entry(row.symbol),),
                                    entry_at=row.entry, seed_regs=regs)
    the_rom_s, _writes, _regs = emu.run(make_image(row.pokes), row.entry, dict(row.regs))
    name, mode, tail = arguments
    assert gd.EXEC.calls(ours.image) == [pexec(mode, name, tail)]
    (parked, saved), = gd.EXEC.parked_at(ours.image)
    assert [(parked, saved)] == gd.EXEC.parked_at(the_rom_s) and saved == THE_DESK_S_SSP != parked
    assert 0 < emu.STACK_TOP - (parked + STACK_KEPT) <= frames.MAX_FRAME_LONGS * aes.LONG_BYTES, "under the caller's own pushes"
    assert case.long_in(ours.image, UDA_SUPER_SP) == THE_DESK_S_SSP
    assert ours.regs["d0"] == answer & aes.LONG_MASK
