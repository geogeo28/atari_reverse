"""THE AES's XBIOS DOOR, trp14 `$fee488` — `src/aes/trp14.S` (what the target ships) and its C twin `trp14.c`.

    move.l (sp)+,$95b2 / trap #14 / move.l $95b2,-(sp) / rts

The door pops its own return address into AES_XBIOS_RETURN, so the trap finds ITS CALLER's frame — the function word
and whatever follows — and returns through that longword. Twenty-one Line-F sites call it, the desk's (band 6) and
ONE of band 5's: sh_main's Getrez (`$feb1ea move.w #4,(sp)`).

  * THE C TWIN serves that one shape — the function word alone — and takes the return address as a host argument
    (the VDI's gemdos_call precedent): verified against the ROM through the machine's OWN XBIOS (Getrez over a
    declared shifter byte), UNPRICED.
  * THE `.S` is the ROM's sixteen bytes, pinned, and BEHAVES as the ROM over the frames its ROM callers push —
    through the transcription relation, the whole register file: over the machine's own XBIOS (Getrez), and over a
    recording `trap #14` (`aes_gemdosif.XBIOS`), where the ledger shows the frame the trap was taken over and the
    script's answer comes back in D0.

WHAT REACHES IT TODAY: any process of the post-boot machine (the desk's own code calls it); the snapshot's
AES_XBIOS_RETURN still holds the return of the desk's last call (`$fe28ec`, after its Blitmode inquiry).
"""
import re
from pathlib import Path

import pytest

from harness import BASE_IMAGE, addrs, emu

import aes
import aes_event
import aes_gemdosif as gd
import case
import test_aes_gsx_transcription as frames
import transcription
import vdi
import vdi_helpers
from case import merge_pokes
from opcodes import DROP_STACK_LONG, RTS

TRP14 = "AES_ROM_TRP14"
# The twin's shape: the return address (a host argument), then the function word.
aes.declare_alcyon(TRP14, aes.LONG_ANSWER, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.WORD_ARG), host_arguments=1)
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))
LINE_F_RETURN_SITE = aes.LINE_F_CALLER_AT + len(DROP_STACK_LONG) + aes.WORD_BYTES
GETREZ = addrs.XBIOS_GETREZ_FN
XBIOS_RETURN = aes.AES_XBIOS_RETURN
STALE_RETURN = {XBIOS_RETURN: vdi.STALE_LONG.to_bytes(aes.LONG_BYTES, "big")}
TRP14_BYTES = 16
REGION = transcription.pinned_region(addrs.AES_ROM_TRP14, addrs.AES_ROM_TRP14 + TRP14_BYTES, TRP14)
# THE TRAP'S SAVE STEERS THE ATTRIBUTION PASS (the bell's reason): the XBIOS dispatcher writes `savptr` itself.
SAVPTR_STEERS_THE_PASS = {"poison": False}
MODES = {"low": 0, "medium": 1, "high": 2}


def own_xbios(pokes=None):
    """The leaf machine with the XBIOS trap's register save in the stack band, the parked return stale."""
    return aes.leaf_machine(onto=merge_pokes(aes_event.savptr_in_the_band(), STALE_RETURN, pokes))


# ---- the C twin, through the machine's own XBIOS ---------------------------------------------------------------------------
def test_the_twin_serves_getrez__held_in_a_child():
    """FIRST, AND IN A CHILD: a twin that refused Getrez would halt by name (`recreate_not_reconstructed`), which in
    this process brings the suite down with no verdict. Here it is a child that did not return."""
    returncode, stderr, _image = aes_event.refusal(TRP14, own_xbios(), (emu.SENTINEL, GETREZ), bind=None, answered=True,
                                                   io_seed={addrs.SHIFTER_RESOLUTION: MODES["medium"]}, read_back=False)
    assert returncode == 0 and vdi_helpers.answer_in(stderr) == MODES["medium"], stderr


@THROUGH
@pytest.mark.parametrize("mode", MODES.values(), ids=MODES)
def test_the_twin_parks_its_caller_s_return_and_answers_getrez(mode, through_line_f):
    """sh_main's call: the function word 4 alone. The ROM's door into the ROM's XBIOS, ours into Getrez's C core:
    the resolution the shifter holds (a declared byte), and the caller's return address parked."""
    site = LINE_F_RETURN_SITE if through_line_f else emu.SENTINEL
    result = aes.run_function(TRP14, (GETREZ,), own_xbios(), through_line_f=through_line_f, host_arguments=(site,),
                              io_seed={addrs.SHIFTER_RESOLUTION: mode}, **SAVPTR_STEERS_THE_PASS)
    assert (result.long_answer(), result.long(XBIOS_RETURN)) == (mode, site)


def test_the_twin_halts_by_name_over_any_other_function():
    """The twin is ONE shape of a door that takes any: Blitmode's frame (the desk's) is the `.S`'s — off target the
    C refuses it by name, in a child."""
    import vdi_helpers
    returncode, stderr, _image = vdi_helpers.refusal_over(
        "aes_trp14", own_xbios(), arguments=(("ctypes.c_uint32", hex(emu.SENTINEL)), ("ctypes.c_uint16", hex(gd.XBIOS_BLITMODE))),
        read_back=False)
    assert returncode != 0 and "trp14" in stderr and "Getrez" in stderr, stderr


def test_the_snapshot_holds_the_return_of_the_desk_s_last_call_through_the_door():
    """THE ROM-RUN STATE: the capture's AES_XBIOS_RETURN is the word after a Line-F call of the door in the desk's
    range — the door was last taken by the desk, and parked what its Line-F return would come back to."""
    parked = case.long_in(BASE_IMAGE, XBIOS_RETURN)
    sites = {at + aes.WORD_BYTES for word_sites in aes.line_f_call_sites(TRP14).values() for at in word_sites}
    assert parked in sites and len(sites) == 21


# ---- the `.S`: its bytes, and its behaviour over the frames the ROM's callers push ---------------------------------------
def test_the_transcription_is_the_rom_s_bytes_exactly():
    transcription.assert_transcribed(REGION, relocated={})


def test_the_region_is_the_door_alone():
    assert bytes(BASE_IMAGE[REGION.hi - len(RTS):REGION.hi]) == RTS
    assert bytes(BASE_IMAGE[REGION.lo - len(RTS):REGION.lo]) == RTS, "trp13's `rts` ends just before it"


def entered(frame, pokes):
    """`pokes` with the XBIOS `frame` (bytes, padded to longwords) where the frame caller reads it, and that caller."""
    frame += bytes(-len(frame) % aes.LONG_BYTES)
    return frames.frame_caller(len(frame) // aes.LONG_BYTES), merge_pokes(pokes, {frames.FRAME_ARGUMENTS_AT: frame})


def words(*values):
    return vdi.pack_words(*values)


ANSWER = 0x00C0_FFEE                    # what the scripted XBIOS answers: no function's own
# (the frame its caller pushed, the machine, the I/O it declares) — over the machine's own XBIOS, then the recorder
OWN = {"Getrez, medium resolution": (words(GETREZ), own_xbios, {addrs.SHIFTER_RESOLUTION: MODES["medium"]}),
       "Getrez, high resolution": (words(GETREZ), own_xbios, {addrs.SHIFTER_RESOLUTION: MODES["high"]})}
BLITMODE_INQUIRY = words(gd.XBIOS_BLITMODE, 0xFFFF)         # the desk's `$fe28e2..$fe28ea`
ARGUMENT_CLASS = "ARGUMENT CLASS"
A_WORD_AND_A_LONG = words(gd.XBIOS_A_MADE_UP_LONG) + (0x0012_3456).to_bytes(aes.LONG_BYTES, "big")  # `$fedaee..$fedaf4`'s WIDTH
RECORDED = {
    "the function word alone (sh_main's Getrez)": (words(GETREZ), [gd.XBIOS.call(GETREZ)]),
    "a function and a word (the desk's Blitmode inquiry)": (BLITMODE_INQUIRY, [gd.XBIOS.call(gd.XBIOS_BLITMODE, ("w", 0xFFFF))]),
    f"{ARGUMENT_CLASS} (a made-up frame, no ROM caller's): a function and a longword":
        (A_WORD_AND_A_LONG, [gd.XBIOS.call(gd.XBIOS_A_MADE_UP_LONG, ("l", 0x0012_3456))]),
}


def recorded_machine():
    return aes.leaf_machine(onto=merge_pokes(STALE_RETURN, gd.XBIOS.pokes([ANSWER])))


@pytest.mark.parametrize("shape", OWN)
def test_the_transcription_behaves_as_the_rom_over_the_machine_s_own_xbios(shape):
    frame, machine, io_seed = OWN[shape]
    caller, staged = entered(frame, machine())
    transcription.run_transcription(TRP14, staged, caller=caller, io_seed=io_seed)


@pytest.mark.parametrize("shape", RECORDED)
def test_the_transcription_takes_the_trap_over_its_caller_s_frame(shape):
    """Both shores trap into the recording handler: the ledger holds THE CALLER'S FRAME — the function word and the
    bytes that follow it — so the door popped exactly its own return address; the answer comes back in D0 (the
    whole register file is compared); and the ROM's own run shows the ledger its name says."""
    frame, calls = RECORDED[shape]
    caller, staged = entered(frame, recorded_machine())
    transcription.run_transcription(TRP14, staged, caller=caller)
    direct = merge_pokes(recorded_machine(), {emu.STACK_TOP + aes.LONG_BYTES: frame})
    final, _writes, regs = emu.run(vdi.make_image(direct), addrs.AES_ROM_TRP14, {})
    assert gd.XBIOS.calls(final) == calls and regs["d0"] == ANSWER
    assert case.long_in(final, XBIOS_RETURN) == emu.SENTINEL


# ---- WHAT THE DOOR MAY LEAVE CHANGED (F4) -----------------------------------------------------------------------------------
# The door serves ANY XBIOS function, and what comes back in the registers is the function's: the XBIOS's dispatcher
# keeps D3-D7/A3-A7 and no more. Every case above reaches Getrez or the recorder, which change none — so the row's
# declared set is the CONTRACT (`xbios/xbios.h`, XBIOS_TRAP_CLOBBERS: what the C twin's own trap names), not a
# measurement of these cases, and a caller's thunk saves D2 and A2 round the door.
GCC_SCRATCH = ("d0", "d1", "a0", "a1")  # the GCC m68k ABI: a callee's to change, so no row declares them
INCLUDE = Path(__file__).resolve().parents[1] / "include"


def _trap_clobbers(header, macro):
    """The registers the clobber list `macro` of `include/<header>` names — a `#define` of another list followed
    (the XBIOS's is the BIOS's)."""
    body = re.search(rf"^#define {macro}\s+(.*)$", (INCLUDE / header).read_text(), re.M).group(1)
    return re.findall(r'"([da]\d)"', body) or _trap_clobbers("bios/bcon.h", body.strip())


def test_the_door_s_row_declares_what_any_xbios_function_may_change():
    """THE RED for a row measured over Getrez alone (the empty set): the declared registers are the trap's published
    contract less the ABI's scratch — D2 and A2."""
    declared = transcription.TRANSCRIBED[TRP14.lower()]
    kept_less = tuple(register for register in _trap_clobbers("xbios/xbios.h", "XBIOS_TRAP_CLOBBERS")
                      if register not in GCC_SCRATCH)
    assert declared == kept_less == ("d2", "a2")


# ---- Tier 3's rows ------------------------------------------------------------------------------------------------------------
# THE C TWIN IS VERIFIED AND UNPRICED (registered so: swept with the registry, listed in the census
# `test_tier3.UNPRICED_AT_A_ROM_ENTRY`): it takes its caller's return site as a host argument, and the door ships
# as its `.S`, whose rows follow.
gd.register_unpriced("Getrez, medium resolution (the C twin: a host argument, and the `.S` ships)", TRP14, (GETREZ,),
                     own_xbios(), io_seed={addrs.SHIFTER_RESOLUTION: MODES["medium"]})
for _shape, (_frame, _machine, _io_seed) in OWN.items():
    _caller, _staged = entered(_frame, _machine())
    transcription.register_transcription(TRP14, _shape, _staged, caller=_caller, io_seed=_io_seed)
for _shape, (_frame, _calls) in RECORDED.items():
    _caller, _staged = entered(_frame, recorded_machine())
    transcription.register_transcription(TRP14, f"{_shape}, the trap recorded", _staged, caller=_caller)
