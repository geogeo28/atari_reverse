"""THE DESK DOOR ON TARGET (`include/aes/deskdoor.h`), read off both blobs' own instructions.

sh_main and sh_cmd call six routines out of the shell: the ROM's deskmain, the desk's four built-ins (band 6's: the
ROM's own addresses until slice F4, their thunks of the table since) and dos_exec (ours: `gemdosif.S`). RULING W4-R4, THE ROM-DEPTH RULE: at each of them PD0's
stack pointer is the ROM's. The door makes it so — it keeps our SP, stands the SP where the ROM's own frames leave
it, lays the ROM's frame, calls, and puts ours back — and HALTS, never shifts, where our own frames run deeper than
the ROM's or the call is made on another stack than PD0's.

WHAT IS HELD HERE, and it is all a reading of the build:
  * THE NUMBERS: where the ROM's SP stands, re-derived from the ROM's own prologues (gem_entry's `jsr`, gem_main's,
    sh_main's and sh_cmd's `link` / `movem`) — and equal to the one figure measured on a boot (deskmain entered at
    `$a364`: band 5 wave 4's design, p5).
  * EACH OF THE SIX SITES, on each blob: the door's nine steps round the ROM's own frame instructions, their
    immediates the header's — one site per routine, in the function the ROM calls it from.
  * THE SHELL'S OWN SHARE OF THE DEPTH: what our sh_main and sh_cmd push before a door, against the ROM's — at or
    under it at every site.

WHAT IS NOT: A RUN. No machine enters sh_main on a blob before the our-boot slice; the halt has never been taken, the
SP at deskmain's entry never read on ours. And THE REST OF THE DEPTH is not this file's: gem_main's frame (and its
entry's glue) lies above sh_main's, and the door fits only where gem_main calls sh_main with its SP at or above the
ROM's `$a386` — `OUR_SLACK` below says by how much each site could give.
"""
import re
from collections import namedtuple

import pytest

from harness import BASE_IMAGE, addrs, bench_tier3

import aes
import aes_geminit as gi
import aes_shmain as sm
import case
import transcription

DOOR = sm.DOOR
BLOBS = {"the bench blob": lambda: bench_tier3().BUILT_ELF, "the shipped blob": lambda: transcription.SHIPPED_ELF}
EACH_BLOB = pytest.mark.parametrize("blob", BLOBS)
LONG = aes.LONG_BYTES
PD0_TOP = aes.AES_UDA1
SP_IN_SH_MAIN, SP_IN_SH_CMD, SP_AT_DOS_EXEC = 0xA368, 0xA356, 0xA35E      # `aes/deskdoor.h`'s, _Static_asserted there
SCRATCH_SLOT = DOOR["DESK_DOOR_SCRATCH_SLOT"]

# ---- the ROM's own frames -----------------------------------------------------------------------------------------------------
LINK_A6, MOVEM_PUSH, JSR_LONG, MOVEA_A6_SP = 0x4E56, 0x48E7, 0x4EB9, 0x2E4E
GEM_ENTRY_S_JSR = gi.LEAVES_THE_FIRST_STACK_AT + aes.WORD_BYTES        # `jsr $fda062`, right after `movea.l a6,sp` ($fd9fbc)
GEM_MAIN = addrs.AES_ROM_GEM_MAIN
DESKMAIN_ENTERED_AT = 0xA364            # MEASURED on the ROM's own boot (the design's p5): the one figure not read


def frame_of(routine):
    """The bytes an Alcyon routine at `routine` pushes under its return address: `link a6,#-n`, then its `movem`."""
    assert case.word_in(BASE_IMAGE, routine) == LINK_A6 and case.word_in(BASE_IMAGE, routine + 4) == MOVEM_PUSH
    locals_ = -aes.signed(case.word_in(BASE_IMAGE, routine + 2))
    return LONG + locals_ + LONG * bin(case.word_in(BASE_IMAGE, routine + 6)).count("1")


def test_the_rom_s_sp_at_each_call_is_what_its_own_prologues_leave():
    """PD0's stack from its top: gem_entry stands the SP there and `jsr`s gem_main; gem_main's frame, a Line-F
    call's return, sh_main's frame — the SP at sh_main's calls; a Line-F call's return and sh_cmd's frame — the SP at
    sh_cmd's. Equal to the header's three, and deskmain's entry is the one a boot measured."""
    assert (case.word_in(BASE_IMAGE, GEM_ENTRY_S_JSR - 2), case.word_in(BASE_IMAGE, GEM_ENTRY_S_JSR)) == (MOVEA_A6_SP, JSR_LONG)
    assert case.long_in(BASE_IMAGE, GEM_ENTRY_S_JSR + 2) == GEM_MAIN
    in_gem_main = PD0_TOP - LONG - frame_of(GEM_MAIN)
    in_sh_main = in_gem_main - LONG - frame_of(addrs.AES_ROM_SH_MAIN)
    in_sh_cmd = in_sh_main - LONG - frame_of(addrs.AES_ROM_SH_CMD)
    assert (in_gem_main, in_sh_main, in_sh_cmd) == (0xA386, SP_IN_SH_MAIN, SP_IN_SH_CMD)
    assert in_sh_main - LONG == DESKMAIN_ENTERED_AT
    assert in_sh_main - DOOR["DOS_EXEC_PUSHED_BYTES"] - LONG == SP_AT_DOS_EXEC


def test_the_frames_the_door_lays_are_the_rom_s_instructions():
    """What the ROM's sh_main and sh_cmd push for each call, read off the ROM: nothing for deskmain; a longword
    stored AT the SP for a file routine; one stored there and one pushed for a disk routine; and for dos_exec the
    tail stored, the mode's word and the name pushed."""
    def words(at, count):
        return tuple(case.word_in(BASE_IMAGE, at + 2 * nth) for nth in range(count))
    assert words(0xFEB1DA, 2) == (0xF9B8, 0xF9BC), "desk_alloc's call word, then deskmain's: nothing pushed between"
    assert words(0xFEB320, 2) == (0x2E8D, 0xF9CC) and words(0xFEB354, 2) == (0x2E8D, 0xF9D0), "move.l a5,(sp) / the call"
    for at, call_word in ((0xFEB36A, 0xF9D4), (0xFEB388, 0xF9D8)):
        assert words(at, 5) == (0x2EB9, 0x0000, 0xC79E, 0x2F0D, call_word), "move.l $c79e,(sp) / move.l a5,-(sp) / the call"
    assert words(0xFEB29C, 3) == (0x2EB9, 0x0000, 0xC82A) and words(0xFEB2A2, 1) == (0x4267,), "the tail stored; clr.w -(sp)"
    assert words(0xFEB2A4, 4) == (0x2F39, 0x0000, 0xC79E, 0xF9C8), "move.l $c79e,-(sp) / dos_exec's call word"


# ---- the six sites, on each blob ---------------------------------------------------------------------------------------------------
Site = namedtuple("Site", "holder target rom_sp slot frame")
# The frame's instructions between the SP's move and the `jsr`, as words: the registers are the door's (A0 the
# longword pushed last, A1 the one before it, D1 a word).
STORE_A0, STORE_A1, PUSH_A0, PUSH_D1_W = 0x2E88, 0x2E89, 0x2F08, 0x3F01
FILE_FRAME, DISK_FRAME, DOS_EXEC_FRAME = (STORE_A0,), (STORE_A1, PUSH_A0), (STORE_A1, PUSH_D1_W, PUSH_A0)
DOS_EXEC = "aes_rom_dos_exec"
# The desk's four built-ins, ours since band 6 slice F4: sh_cmd's door `jsr`s each one's thunk of the table
# (`transcription.DESK_DOOR_THUNKS`, bound by the generated `include/aes/lineftable.h`).
DOOR_THUNK = {name: thunk for thunk, name in transcription.DESK_DOOR_THUNKS.items()}
SITES = {
    "deskmain": Site("aes_sh_main", DOOR_THUNK["AES_ROM_DESKMAIN"], SP_IN_SH_MAIN, 0, ()),     # its thunk since band 6 W3b
    "dos_exec": Site("aes_sh_main", DOS_EXEC, SP_IN_SH_MAIN, SCRATCH_SLOT, DOS_EXEC_FRAME),
    "show a file": Site("aes_sh_cmd", DOOR_THUNK["AES_ROM_DESK_SHOW_FILE"], SP_IN_SH_CMD, SCRATCH_SLOT, FILE_FRAME),
    "print a file": Site("aes_sh_cmd", DOOR_THUNK["AES_ROM_DESK_PRINT_FILE"], SP_IN_SH_CMD, SCRATCH_SLOT, FILE_FRAME),
    "format": Site("aes_sh_cmd", DOOR_THUNK["AES_ROM_DESK_FORMAT"], SP_IN_SH_CMD, SCRATCH_SLOT, DISK_FRAME),
    "copy a disk": Site("aes_sh_cmd", DOOR_THUNK["AES_ROM_DESK_COPY_DISK"], SP_IN_SH_CMD, SCRATCH_SLOT, DISK_FRAME),
}
KEEP_SP, CMPA_L_SP, BCS_S, BLS_S, TRAP_7, MOVEA_L_SP, PUT_SP_BACK = 0x260F, 0xBFFC, 0x65, 0x63, 0x4E47, 0x2E7C, 0x2E43
_A_LINE = re.compile(r"^\s*([0-9a-f]+):\t((?:[0-9a-f]{4} )+)", re.M)


def words_of(elf, function):
    """`[(address, word), ...]`: the words of `function` in `elf`'s listing, in order."""
    (lo, hi), = bench_tier3()._function_ranges(elf)[function]
    found = []
    for at, hexes in _A_LINE.findall(transcription.listing(elf)):
        start = int(at, 16)
        if lo <= start < hi:
            found += [(start + 2 * nth, int(word, 16)) for nth, word in enumerate(hexes.split())]
    assert found and found[0][0] == lo, f"{function} is not in the listing where the symbol table has it"
    return found


def address_of(elf, target):
    if isinstance(target, int):
        return target
    (symbol,) = [symbol for symbol in transcription.symbol_table(elf) if symbol.name == target]
    return symbol.start


def long_words(value):
    return [value >> 16, value & 0xFFFF]


def door_as_laid(site, target):
    """The door's words for `site`: the SP kept (D3: a register an Alcyon callee keeps); the vet — below the ROM's
    SP and its slot, or above PD0's top, the halt —; the SP stood at the ROM's; the frame; the call; the SP back."""
    return [KEEP_SP, CMPA_L_SP, *long_words(site.rom_sp + site.slot), BCS_S << 8 | 8, CMPA_L_SP, *long_words(PD0_TOP),
            BLS_S << 8 | 2, TRAP_7, MOVEA_L_SP, *long_words(site.rom_sp), *site.frame, JSR_LONG, *long_words(target),
            PUT_SP_BACK]


@EACH_BLOB
@pytest.mark.parametrize("name", SITES)
def test_a_call_out_of_the_shell_is_the_door_s_steps_round_the_rom_s_frame(name, blob):
    """ONE site of the routine in the whole blob, inside the function the ROM calls it from, and at it the door
    whole: every step, in order, the three immediates the header's."""
    elf, site = BLOBS[blob](), SITES[name]
    target = address_of(elf, site.target)
    listed = [word for _at, word in words_of(elf, site.holder)]
    expected = door_as_laid(site, target)
    starts = [nth for nth in range(len(listed)) if listed[nth:nth + len(expected)] == expected]
    assert len(starts) == 1, f"{site.holder} holds the door of {name} {len(starts)} times"
    # ...AND NOTHING OF AN EARLIER CALL IS STILL ON THE STACK THERE: -O2 leaves a call's arguments pushed and pops
    # several calls' at once (`stack_diet.h`, no-defer-pop) — bytes the door's vet would count as our frame's, and
    # halt for. Where it does, the pop is the very next instruction after the door.
    after = listed[starts[0] + len(expected)]
    assert after != LEA_SP_SP and after & ADDQ_L_SP_MASK != ADDQ_L_SP, (
        f"{name}: the door is taken with an earlier call's arguments still pushed (popped right after it)")
    if isinstance(site.target, int):    # ...the ROM's routine: the blob's one `jsr` of it (`tier3.rom_calls_owed`)
        assert list(bench_tier3().rom_calls_owed(elf).values()).count(target) == 1
    else:                               # ...an entry of ours (dos_exec's `.S`, a built-in's thunk): nothing else calls it
        assert [function for function, callees in transcription.call_graph(elf).items() if site.target in callees] == [site.holder]


@EACH_BLOB
def test_the_rom_routines_the_door_calls_are_the_ones_tier_3_declares_owed(blob):
    """THE ONE-SITE RULE, extended to the door (`bench/tier3.py`, ROM_CALLS_OWED_TO_A_LATER_BAND; `test_tier3.py`
    holds every entry to one site in its function): the blob's `jsr`s into the AES's ROM text that the table names
    are exactly the door's ROM routines — deskmain alone since band 6 slice F4 flipped the four built-ins, NONE since
    band 6 W3b flipped deskmain —, each held by the function declared."""
    owed = bench_tier3().rom_calls_owed(BLOBS[blob]())
    the_door_s = {routine: holder for routine, (holder, _why) in bench_tier3().ROM_CALLS_OWED_TO_A_LATER_BAND.items()
                  if holder in ("aes_sh_main", "aes_sh_cmd")}
    assert the_door_s == {site.target: site.holder for site in SITES.values() if isinstance(site.target, int)}
    assert sorted(owed.values()) == sorted(bench_tier3().ROM_CALLS_OWED_TO_A_LATER_BAND)
    assert bench_tier3().door_calls(BLOBS[blob]()) == {}, "no other `jsr` of the build lands in the AES's ROM text"


# ---- the shell's own share of the depth ------------------------------------------------------------------------------------------
PUSH_LONG_REGISTER_MASK, PUSH_LONG_REGISTER = 0xFFF0, 0x2F00      # move.l dn/an,-(sp)
SUBQ_L_SP_MASK, SUBQ_L_SP = 0xF1FF, 0x518F                       # subq.l #n,sp
LEA_SP_SP = 0x4FEF                                               # lea d16(sp),sp
ADDQ_L_SP_MASK, ADDQ_L_SP = 0xF1FF, 0x508F                       # addq.l #n,sp
C_CALL_BYTES = 2 * LONG                 # what a C call of one argument puts under its caller's SP: the image, the return
LINE_F_CALL_BYTES = LONG                # ...and a Line-F call of the ROM's: the return alone


def pushed_by_its_prologue(elf, function):
    """The bytes `function` pushes before its first instruction that is no push: its saved registers and its locals."""
    words, pushed, nth = [word for _at, word in words_of(elf, function)], 0, 0
    while True:
        word = words[nth]
        if word == MOVEM_PUSH:
            pushed, nth = pushed + LONG * bin(words[nth + 1]).count("1"), nth + 2
        elif word & PUSH_LONG_REGISTER_MASK == PUSH_LONG_REGISTER:
            pushed, nth = pushed + LONG, nth + 1
        elif word & SUBQ_L_SP_MASK == SUBQ_L_SP:
            pushed, nth = pushed + (((word >> 9) & 7) or 8), nth + 1
        elif word == LEA_SP_SP:
            pushed, nth = pushed - aes.signed(words[nth + 1]), nth + 2
        else:
            return pushed


# How far ABOVE its floor our SP stands at each site WHERE gem_main CALLS sh_main WITH ITS SP AT THE ROM'S ($a386):
# the bytes gem_main's own frame (and its entry's) may run deeper than the ROM's before that door halts. THE SHELL'S
# SHARE ALONE: with gem_main as it is built (its SP at `$a39a` there — 20 above the ROM's) each is 20 more, the
# margins 26 / 22 / 20 that `test_aes_stack.py` reads off the whole path and holds (THE_DOORS; sh_main's entry measured).
OUR_SLACK = {"deskmain": 6, "dos_exec": 2, "show a file": 0, "print a file": 0, "format": 0, "copy a disk": 0}


@EACH_BLOB
@pytest.mark.parametrize("name", SITES)
def test_the_shell_s_own_frames_are_no_deeper_than_the_rom_s_at_a_door(name, blob):
    """From gem_main's SP at its call of sh_main down to the door: ours — a C call, sh_main's saved registers, and for
    sh_cmd's doors a C call and its saved registers more — against the ROM's Line-F return and Alcyon frames, with the
    call's own slot left free. NEVER DEEPER, at any of the six; the slack is pinned so that a frame that grows says
    which door it takes the room of."""
    elf, site = BLOBS[blob](), SITES[name]
    ours = C_CALL_BYTES + pushed_by_its_prologue(elf, "aes_sh_main")
    the_rom_s = LINE_F_CALL_BYTES + frame_of(addrs.AES_ROM_SH_MAIN)
    if site.holder == "aes_sh_cmd":
        ours += C_CALL_BYTES + pushed_by_its_prologue(elf, "aes_sh_cmd")
        the_rom_s += LINE_F_CALL_BYTES + frame_of(addrs.AES_ROM_SH_CMD)
    assert 0xA386 - the_rom_s == site.rom_sp
    slack = the_rom_s - site.slot - ours
    assert slack >= 0, f"our frames are {-slack} bytes deeper than the ROM's at {name}: the door would halt"
    assert slack == OUR_SLACK[name], f"{name}: {slack} bytes of slack, {OUR_SLACK[name]} pinned — say what moved"


@EACH_BLOB
def test_sh_cmd_is_called_from_sh_main_s_own_body(blob):
    """sh_cmd's doors are two frames deep, and the depth above counts ONE C call between them: sh_main's own call of
    sh_cmd, not one made through a step of its loop (a step's frame would lie between, uncounted)."""
    elf = BLOBS[blob]()
    callers = [function for function, callees in transcription.call_graph(elf).items() if "aes_sh_cmd" in callees]
    assert callers == ["aes_sh_main"]


@EACH_BLOB
def test_sh_find_is_handed_our_sh_show_on_target(blob):
    """THE BY-VALUE SITE (`$feb272 move.l #$feaddc,(sp)`), on target: the step that calls sh_find names the build's own
    entry of sh_show — which calls the C — and no word of either blob names the ROM's. (Off target the routine is the
    hook's key, and WHAT IT DOES FROM sh_main IS NOTHING: sh_main sets sh_dodef before sh_find, so sh_show's two
    sh_draw draw nothing — no Tier 1 row of sh_main can tell a sh_find handed no routine. This reading is what holds
    that one is.)"""
    elf = BLOBS[blob]()
    graph = transcription.call_graph(elf)
    assert {"aes_sh_find", "sh_show_entry"} <= set(graph["the_command_is_found"]) and "aes_sh_show" in graph["sh_show_entry"]
    by_value = [word for words in (words_of(elf, "the_command_is_found"),) for _at, word in words]
    the_rom_s = long_words(addrs.AES_ROM_SH_SHOW)
    assert not _holds_the_words(by_value, the_rom_s), "the step hands sh_find the ROM's sh_show by its address"


def _holds_the_words(words, sequence):
    return any(words[nth:nth + len(sequence)] == sequence for nth in range(len(words)))
