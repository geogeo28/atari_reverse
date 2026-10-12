"""gem_main (`src/aes/geminit.c`, `$fda062`) AS BOTH BUILDS COMPILE IT — what can be held of a routine that returns
on no machine a boot makes (ruling W4-R5: verified on the blobs at checkpoints, slice B's; its host twin run where a
stretch is a call with a return — the first stretch and the reader, `test_aes_geminit_boot.py`).

HELD HERE, off the builds themselves:
  * IT IS THERE, UNDER THE NAMES gem_entry AND THE HOST CALL IT BY: `aes_rom_gem_main` in both blobs — the entry
    gemstart's `jsr` names, taking nothing — and `aes_gem_main` in the host library, with its first stretch.
  * IT CALLS WHAT THE ROM'S CALLS, AND NOTHING ELSE: every routine the ROM's gem_main reaches by a Line-F word is
    called by ours, on both blobs — but the two mask brackets, the same two instructions inline (`aes/switch.h`), and
    this file's own three leaves where GCC inlined them, whose own callees stand in — and ours calls nothing more.
  * THE SHELL IS CALLED OVER A FRAME NO DEEPER THAN THE ROM'S: sh_main, the desk and every program it starts run
    UNDER gem_main's frame for the whole session (ruling W4-R4: the desk's frames must lie where the ROM's lie, by a
    named pad in the desk door). What gem_main itself holds there is read off both blobs — the image base and one
    saved register — against the ROM's `link a6,#-8` and three registers.

NOT HELD HERE: the ORDER of gem_main's calls and what each is handed (the blobs' boot at its checkpoints, slice B);
the teardown, which no boot reaches (the served class, slice B).
"""
import re

import pytest

from harness import BASE_IMAGE, _lib, addrs

import aes
import aes_geminit as gi
import aes_switch as switch
import case
import rom_data
import routines
import transcription

ENTRY, SHELL = "aes_rom_gem_main", "aes_sh_main"
GEM_MAIN, GEM_MAIN_EXIT = addrs.AES_ROM_GEM_MAIN, addrs.AES_ROM_PINIT - aes.WORD_BYTES
ELFS = {"the bench blob": transcription.BENCH_ELF, "the shipped blob": transcription.SHIPPED_ELF}
# gem_main's three stretches, routines of their own on target (`geminit.c` says why), and gem_main itself.
STRETCHES = ("lay_the_processes", "bring_gem_up", "take_gem_down")
# WHAT THE ROM CALLS BY A LINE-F WORD AND A BUILD DOES NOT CALL: the mask brackets — `move.w sr,<save> / ori.w
# #$700,sr` and back, the same two instructions inline in C (`aes/switch.h`).
INLINE_ON_TARGET = {"AES_ROM_SPL7_SAVE", "AES_ROM_SPL_RESTORE"}
# ...and this file's own leaves, which GCC may inline into a stretch: then THEIR callees are the stretch's.
LEAVES_OF_THIS_FILE = ("aes_ini_dlongs", "aes_pinit", "aes_all_run")


_PUSH = re.compile(r"^(?:movel|pea) .*,?%sp@-$|^pea ")
_STORE_AT_SP = re.compile(r"^movel %[ad]\d,%sp@$")
_POP = re.compile(r"^movel %sp@\+,%[ad]\d$")
_DROP = re.compile(r"^addql #(\d),%sp$")
_NO_STACK = re.compile(r"^(?:moveq #-?\d+,%d\d|rts)$")
_CALL = re.compile(r"^jsr .*<(\w+)>\)?$")


@pytest.fixture(scope="module", params=ELFS.values(), ids=ELFS)
def elf(request):
    return str(request.param)


def the_rom_s_callees():
    """The `addrs.h` names of every routine the ROM's gem_main reaches by a Line-F CALL word, in its text's order."""
    named = {getattr(addrs, name): name for name in dir(addrs) if routines.is_routine(name, (routines.AES_PREFIX,))}
    words = [at for at, text in rom_data.instructions(GEM_MAIN, GEM_MAIN_EXIT) if text is None]
    targets = [aes.line_f_target(case.word_in(BASE_IMAGE, at)) for at in words]
    assert all(target in named for target in targets), "gem_main calls a routine `addrs.h` does not name"
    return [named[target] for target in targets]


def called_as(name):
    """The symbol a build calls the ROM routine `name` by: an entry of the switch's `.S` under its own name (cli, sti,
    dsptch), else its C core."""
    entry = name.lower()
    if entry in transcription.SWITCH_ENTRIES:
        return entry
    return "aes_dsptch" if name == "AES_ROM_DSPTCH" else routines.core_symbol(name)


def test_the_host_library_and_both_blobs_have_gem_main(elf):
    """COMPILED ON BOTH BUILDS: the target's entry — the one gemstart's `jsr` names — in each blob; the host's core and
    its first stretch in the library; and no blob carries the host's names."""
    symbols = {symbol.name for symbol in transcription.symbol_table(elf)}
    assert ENTRY in symbols and not {"aes_gem_main", "aes_gem_main_lays_the_processes"} & symbols
    assert hasattr(_lib, "aes_gem_main") and hasattr(_lib, "aes_gem_main_lays_the_processes") and not hasattr(_lib, ENTRY)
    assert set(STRETCHES) <= symbols and "aes_gem_read_inf" in symbols


def test_gem_main_is_its_three_stretches_round_the_shell(elf):
    graph = transcription.call_graph(elf)
    assert graph[ENTRY] == {*STRETCHES, SHELL}
    order = [found.group(1) for _at, text in switch.listed_functions(elf)[ENTRY] if (found := _CALL.match(text))]
    assert order == ["lay_the_processes", "bring_gem_up", SHELL, "take_gem_down"]


def test_gem_main_calls_what_the_rom_s_calls_and_nothing_else(elf):
    """THE CALLEES, both ways: the ROM's Line-F targets as a build calls each, against the union of the stretches'
    callees off the blob's call graph (a call through a register included: `transcription.call_graph`)."""
    graph = transcription.call_graph(elf)
    ours = set().union(*(graph[stretch] for stretch in STRETCHES)) | graph[ENTRY] - set(STRETCHES)
    expected = {called_as(name) for name in the_rom_s_callees() if name not in INLINE_ON_TARGET}
    inlined = {leaf for leaf in LEAVES_OF_THIS_FILE if leaf not in ours}
    stand_ins = set().union(*(graph[leaf] for leaf in inlined)) if inlined else set()
    assert ours == (expected - inlined) | stand_ins, (
        f"called and not the ROM's: {sorted(ours - expected - stand_ins)}; the ROM's and not called: "
        f"{sorted(expected - inlined - ours)}")
    assert set(LEAVES_OF_THIS_FILE) <= expected and {"aes_rom_cli", "aes_rom_sti", "aes_dsptch", SHELL, "aes_gem_read_inf"} <= expected


def test_the_rom_s_gem_main_makes_forty_five_line_f_calls_of_thirty_three_routines():
    """THE LIST ITSELF, pinned as the ROM has it: the mask brackets five times each, rs_gaddr four, gsx_tick twice."""
    callees = the_rom_s_callees()
    assert (len(callees), len(set(callees))) == (45, 33)
    assert callees.count("AES_ROM_SPL7_SAVE") == callees.count("AES_ROM_SPL_RESTORE") == 5
    assert callees.count("AES_ROM_RS_GADDR") == 4 and callees.count("AES_ROM_GSX_TICK") == 2
    assert callees[0] == "AES_ROM_INI_DLONGS" and callees[-1] == "AES_ROM_SPL_RESTORE"
    assert callees.index("AES_ROM_SH_MAIN") == callees.index("AES_ROM_ALL_RUN") + 1


# ---- the frame the shell runs under ----------------------------------------------------------------------------------------


def depths_at_its_calls(elf):
    """`{callee: bytes}`: how far below the stack pointer it was entered on `aes_rom_gem_main` stands at each call —
    read off its listing, which is straight-line code: every instruction is one of six shapes or the read refuses."""
    depth, at_calls = 0, {}
    for at, text in switch.listed_functions(elf)[ENTRY]:
        call, drop = _CALL.match(text), _DROP.match(text)
        if call:
            at_calls[call.group(1)] = depth
        elif _PUSH.match(text):
            depth += aes.LONG_BYTES
        elif _POP.match(text):
            depth -= aes.LONG_BYTES
        elif drop:
            depth -= int(drop.group(1))
        else:
            assert _STORE_AT_SP.match(text) or _NO_STACK.match(text), f"{ENTRY} at {at:#x}: `{text}` — a shape this read does not know"
    assert depth == 0, f"{ENTRY} returns {depth} bytes off the stack it was entered on"
    return at_calls


def the_rom_s_frame():
    """What the ROM's gem_main holds under each of its calls: its `link`'s saved A6 and locals, and the registers its
    `movem` saves — read off its first two instructions."""
    (_at, link), (_at2, movem) = rom_data.instructions(GEM_MAIN, GEM_MAIN + 2 * aes.LONG_BYTES)[:2]
    locals_bytes = -int(re.fullmatch(r"linkw %fp,#(-\d+)", link).group(1))
    saved = re.fullmatch(r"moveml (.+),%sp@-", movem).group(1)
    registers = sum(1 if "-" not in part else int(part[-1]) - int(part.split("-")[0][-1]) + 1 for part in saved.split("/"))
    return aes.LONG_BYTES + locals_bytes + aes.LONG_BYTES * registers


THE_ROM_S_FRAME = 24                    # `link a6,#-8` and D6, D7, A5
OUR_FRAME_UNDER_THE_SHELL = 8           # one saved register and the image base handed the shell


def test_the_shell_is_called_over_a_frame_no_deeper_than_the_rom_s(elf):
    """RULING W4-R4's premise for gem_main: 8 bytes of ours against the ROM's 24 — the shell's return address lies
    SIXTEEN BYTES HIGHER than in the ROM, which the desk door's pad is to make up (slice SH; held on the boot by
    slice B: gem_main's frame + n must move the stack pointer at deskmain's entry by n, or the pad refuses)."""
    assert the_rom_s_frame() == THE_ROM_S_FRAME
    depths = depths_at_its_calls(elf)
    assert set(depths) == {*STRETCHES, SHELL}
    assert depths[SHELL] == OUR_FRAME_UNDER_THE_SHELL <= THE_ROM_S_FRAME
    assert all(depth == OUR_FRAME_UNDER_THE_SHELL for depth in depths.values()), "no stretch leaves anything under the next"


def test_the_frame_read_refuses_an_instruction_it_does_not_know(elf, monkeypatch):
    """ITS RED: a `lea` of the stack pointer among the entry's instructions — a frame of locals — is no shape of the
    read, and is refused by name rather than counted as nothing."""
    listed = dict(switch.listed_functions(elf))
    listed[ENTRY] = [(0, "lea %sp@(-12),%sp"), *listed[ENTRY]]
    monkeypatch.setattr(switch, "listed_functions", lambda _elf: listed)
    with pytest.raises(AssertionError, match="a shape this read does not know"):
        depths_at_its_calls(elf)


def test_the_first_stack_s_words_and_the_tick_s_slot_are_where_gem_entry_lays_them():
    """gem_main READS what gem_entry stored — the tick glue's address for vex_timv, the device and the change word the
    reader and gsx_init read: one address each, the `.S`'s and the C's (`aes/gemstart.h`, `aes/gsxif.h`)."""
    assert gi.STORED_INTO[0xFD9F92] == gi.GEMSTART["AES_TICK_ROUTINE"] == 0x947E
    assert (gi.RESTYPE, gi.RSCHANGE, gi.DISK_USABLE) == (0x8908, 0x890A, 0x8992)
    first_stack = range(gi.GEMSTART["GEM_START_WORD_890C"] + aes.WORD_BYTES, aes.header_constants("aes.h")["AES_SR_DISPATCH"])
    assert len(first_stack) == 134 and gi.GEMSTART["GEM_FIRST_STACK"] + 6 == first_stack.stop
