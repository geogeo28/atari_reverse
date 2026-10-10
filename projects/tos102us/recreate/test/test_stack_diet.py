"""THE FRAME DIET'S MARKS (`include/stack_diet.h`) — a routine on the screen manager's stack, or under a `trap #2`
taken on it, compiled with some of -O2's passes off, by GCC's per-function `optimize` attribute, so that its frame costs what the ROM's does.

GCC documents the attribute as a debugging aid. What holds it is read off the compiler's own output, on every run:

  * A MARK IS ITS FLAGS AND NOTHING ELSE: each marked function, compiled as marked, is instruction for instruction
    what the same source compiles to with the marks off and the mark's flags on the command line — under each blob's
    own flags. A mark that dropped one of the build's flags for its function (`-fno-strict-aliasing`,
    `-fno-jump-tables`, the CPU) would part the two; so would a compiler that ignored the attribute, which the
    premise beside it tells apart (marks off and no flag: other instructions).
  * THE ONE SETTING THE ATTRIBUTE WOULD RESET IS SPELT INSIDE IT: `-ffreestanding` implies no loop-pattern
    recognition, a per-function `optimize` puts -O2's back, and a fill loop then compiles to `jsr memset` in a ROM
    that links none. Both macros that spell an attribute carry `no-tree-loop-distribute-patterns`; a fill loop under
    either stays a loop (and under a bare attribute does not: the premise), no marked function names a library
    routine, and no source spells `optimize(` outside the two macros.
  * WHAT THE MARKS BUY, PINNED: the bench blob's sources linked a second time with every mark off, the screen
    manager's two bounds read off both (`aes_stack`'s reading) — the bytes each bound is deeper without them, and
    for each marked function what it holds on its own deepest path and at its deepest trap, never more with its mark
    than without and less on one of the two.
The cycles a mark costs are Tier 3's (`make bench`: the bar, per row).
"""
import functools
import re
import subprocess

import pytest

from recreate_kit import rom_bench

import aes_stack
import aes_switch
import derived
import transcription

RECREATE = derived.RECREATE
SOURCES = sorted((RECREATE / "src").glob("*/*.c"))
MARKS_OFF = "-DSTACK_DIET_MARKS_OFF"
# A mark, the markers a definition keeps directly above itself (`include/transcribed.h`), and the definition's name.
_A_MARK = re.compile(r"^FRAME_DIET\(([^\n]*)\)\n(?:(?:EVDOOR_TWIN|TRANSCRIBED_CORE)\n)?"
                     r"(?:static )?(?:__attribute__\(\(\w+\)\) )?[\w \*]*?\b(\w+)\(", re.MULTILINE)
_ANY_MARK = re.compile(r"^FRAME_DIET\(", re.MULTILINE)
FLAG_VARIABLES = ("BENCH_CFLAGS", "SHIPPED_CFLAGS")


def _marks():
    """`{function: (its source, the mark's flags as the command line spells them)}` over the AES's C."""
    found = {}
    for source in SOURCES:
        text = source.read_text()
        here = {name: (source, tuple(f"-f{flag.strip().strip(chr(34))}" for flag in flags.split(",")))
                for flags, name in _A_MARK.findall(text)}
        assert len(here) == len(_ANY_MARK.findall(text)), f"{source.name}: a FRAME_DIET mark no definition follows"
        assert not set(here) & set(found), f"two marked functions of one name: {sorted(set(here) & set(found))}"
        found.update(here)
    return found


MARKS = _marks()


@functools.cache
def _expanded(variable):
    return tuple(transcription.make_variable(RECREATE, variable))


@functools.cache
def _assembly(source, variable, extra):
    """`source` as the blob of `variable`'s flags compiles it, with `extra` after them: its assembly."""
    return subprocess.run(["m68k-elf-gcc", *_expanded(variable), *extra, "-S", str(source), "-o", "-"], cwd=RECREATE,
                          capture_output=True, text=True, check=True).stdout


_A_LOCAL_LABEL = re.compile(r"\.L\d+")


def _body(assembly, function):
    """`function`'s instructions in `assembly`, its local labels numbered in the order they appear: a label's own
    number counts the labels of the functions above it, which another flag moves."""
    body = re.search(rf"^{function}:\n(.*?)^\t\.size\t{function},", assembly, re.MULTILINE | re.DOTALL).group(1)
    order = {}
    return _A_LOCAL_LABEL.sub(lambda label: order.setdefault(label.group(0), f".L<{len(order)}>"), body)


def test_the_marks_are_read_off_the_sources():
    assert len(MARKS) == len(BOUGHT_BY_FUNCTION) and "aes_just_draw" in MARKS
    assert all(flag.startswith("-fno-") for _source, flags in MARKS.values() for flag in flags)


@pytest.mark.parametrize("variable", FLAG_VARIABLES)
@pytest.mark.parametrize("function", sorted(MARKS))
def test_a_mark_is_its_flags_on_the_command_line_and_nothing_else(function, variable):
    source, flags = MARKS[function]
    marked = _body(_assembly(source, variable, ()), function)
    assert marked == _body(_assembly(source, variable, (MARKS_OFF, *flags)), function), (
        f"{function} as marked FRAME_DIET{flags} is not what {' '.join(flags)} compiles it to under {variable}: the "
        f"attribute changes more than its flags for this function (`include/stack_diet.h`)")
    assert not _A_LIBRARY_ROUTINE.search(marked), f"{function} as marked calls a library routine a ROM does not link"
    assert marked != _body(_assembly(source, variable, (MARKS_OFF,)), function), (
        f"{function}: the premise — with no mark and no flag it compiles to other instructions (a mark the compiler "
        f"ignores, or one that changes nothing, would pass the comparison above)")


# ---- THE SETTING AN `optimize` ATTRIBUTE RESETS, AND THE TWO MACROS THAT CARRY IT ------------------------------------------------
_A_LIBRARY_ROUTINE = re.compile(r"\b(?:memset|memcpy|memmove|strlen)\b")
A_FILL_LOOP = """
#include <stdint.h>
#include "stack_diet.h"

{attribute}
void fills_sixty_four_bytes(uint8_t *at)
{{
    for (int index = 0; index < 64; index++)
        at[index] = 0;
}}
"""
THE_DIET_S_MARK = 'FRAME_DIET("no-defer-pop")'
THE_JUMP_TABLE_S = '__attribute__((optimize(OPTIMIZE_KEEPS_FREESTANDING_S_LOOPS, "jump-tables")))'
A_BARE_ATTRIBUTE = '__attribute__((optimize("no-defer-pop")))'


def _fill_loop_under(attribute, variable, scratch):
    source = scratch / "fill.c"
    source.write_text(A_FILL_LOOP.format(attribute=attribute))
    return _body(_assembly.__wrapped__(source, variable, ()), "fills_sixty_four_bytes")


@pytest.mark.parametrize("variable", FLAG_VARIABLES)
def test_a_fill_loop_under_either_macro_stays_a_loop_and_under_a_bare_attribute_it_does_not(variable, tmp_path):
    """RED (the review's finding 1): `__attribute__((optimize("no-defer-pop")))` on a zeroing loop compiles, under
    the build's own flags, to `jsr memset`. Under the diet's mark and under the jump table's attribute it stays the
    loop the unmarked source compiles to."""
    unmarked = _fill_loop_under("", variable, tmp_path)
    assert not _A_LIBRARY_ROUTINE.search(unmarked), "the premise: -ffreestanding keeps the loop a loop"
    assert "memset" in _fill_loop_under(A_BARE_ATTRIBUTE, variable, tmp_path), (
        "the premise: a bare `optimize` attribute brings loop-pattern recognition back")
    for attribute in (THE_DIET_S_MARK, THE_JUMP_TABLE_S):
        assert not _A_LIBRARY_ROUTINE.search(_fill_loop_under(attribute, variable, tmp_path)), attribute


_AN_OPTIMIZE_ATTRIBUTE = re.compile(r"__attribute__\(\([^\n]*?\boptimize\(([^\n]*)")
THE_SETTING_KEPT = "OPTIMIZE_KEEPS_FREESTANDING_S_LOOPS"


def test_no_source_spells_an_optimize_attribute_without_the_setting_it_resets():
    """Every `optimize(` of the sources and headers is one of the two macros', and each names the setting first."""
    spelt = {(path.name, found) for path in [*(RECREATE / "src").glob("*/*.c"), *(RECREATE / "include").rglob("*.h")]
             for found in _AN_OPTIMIZE_ATTRIBUTE.findall(path.read_text())}
    assert {name for name, _found in spelt} == {"stack_diet.h", "gemsuper.c"}
    assert all(found.startswith(THE_SETTING_KEPT) for _name, found in spelt), spelt


# ---- WHAT THE MARKS BUY ----------------------------------------------------------------------------------------------------
BENCH = aes_stack.BLOBS["the bench blob"]
# The screen manager's two bounds on the bench blob, in bytes: `(the deepest SP of our own code, the deepest SP a
# `trap #2` is taken at)` — how much deeper each is with every mark off.
BOUGHT = (188, 160)
# ...and each marked function's own frame, `(on its deepest path, at its deepest trap)` — None where no path of its
# takes a trap: `function: (without its mark, with it)`.
BOUGHT_BY_FUNCTION = {
    "aes_amouse": ((60, None), (44, None)),
    "aes_aqueue": ((48, None), (32, None)),
    "aes_b_delay": ((32, None), (20, None)),
    "aes_bb_fill": ((52, 48), (24, 24)),
    "aes_bchange": ((52, None), (32, None)),
    "aes_doq": ((56, None), (40, None)),
    "aes_ev_multi": ((60, 60), (52, 52)),
    "aes_everyobj": ((94, 94), (86, 86)),
    "aes_forker": ((60, 60), (40, 40)),
    "aes_fpdnm": ((80, None), (56, None)),
    "aes_gr_box": ((84, 84), (44, 44)),
    "aes_gr_dragbox": ((112, 112), (88, 88)),
    "aes_gr_gicon": ((116, 116), (72, 68)),
    "aes_gr_rect": ((68, 68), (48, 48)),
    "aes_gr_wait": ((72, 72), (40, 40)),
    "aes_gr_watchbox": ((140, 108), (100, 100)),
    "aes_gsx_blt": ((84, 68), (40, 40)),
    "aes_gsx_tblt": ((60, 60), (36, 36)),
    "aes_hctl_button": ((32, 32), (28, 28)),
    "aes_hctl_rect": ((40, 40), (36, 36)),
    "aes_hctl_window": ((112, 112), (88, 88)),
    "aes_just_draw": ((148, 148), (124, 124)),
    "aes_mchange": ((64, 80), (64, 64)),
    "aes_mn_do": ((132, 132), (104, 104)),
    "aes_mowner": ((28, None), (24, None)),
    "aes_ob_change": ((68, 68), (64, 64)),
    "aes_ob_draw": ((64, 64), (60, 60)),
    "aes_ob_find": ((100, None), (80, None)),
    "aes_post_button": ((48, None), (40, None)),
    "aes_post_mouse": ((48, None), (40, None)),
    "aes_rom_ctlmgr": ((68, 68), (36, 36)),
    "draw_border_and_fill": ((72, 72), (48, 48)),
    "draw_state_marks": ((88, 88), (68, 68)),
    # the VDI's text handler's deep frame, under the trap (no path of the AES's reading: read for itself)
    "place_and_draw": ((76, None), (64, None)),
}


@pytest.fixture(scope="module")
def unmarked_elf(tmp_path_factory):
    """The bench blob's own sources and flags, every mark off, linked as `kit.mk` links the blob: its ELF."""
    elf = tmp_path_factory.mktemp("stack_diet_marks_off") / "bench.elf"
    subprocess.run(["m68k-elf-gcc", *_expanded("BENCH_CFLAGS"), MARKS_OFF, "-Wl,--build-id=none", "-Wl,-e0",
                    f"-Wl,-Ttext={_expanded('BENCH_BASE')[0]}", *_expanded("BENCH_SRC"), *_expanded("BENCH_LDLIBS"), "-o",
                    str(elf)], cwd=RECREATE, capture_output=True, text=True, check=True)
    return elf


# A routine that calls what it is handed is read once for each routine a caller hands it (`aes_switch.HANDED`):
# everyobj's frame is read under the walk the deepest paths make, ob_draw's.
THE_WALK_S_ROUTINE = "aes_just_draw_alcyon"


def _frames(read, function):
    """What `function` holds itself in the reading `read`: `(on its deepest path, at its deepest trap or None)`."""
    name = f"{function}{aes_switch.HANDED}{THE_WALK_S_ROUTINE}" if function in aes_stack.CALLS_WHAT_IT_IS_HANDED else function
    use = read.of(name)
    return read.chain(name)[0][1], None if use.at_a_trap is None else read.chain(name, to_the_trap=True)[0][1]


def test_the_marks_buy_what_is_pinned_and_each_its_own_function_a_smaller_frame(unmarked_elf):
    """ONE TEST for the two holds: the second link is the cost, made once."""
    without, marked = aes_stack.reading(unmarked_elf), aes_stack.reading(rom_bench.RomBench(BENCH).elf)
    entry = aes_stack.SCREEN_MANAGER_ENTRY
    bought = (without.of(entry).deepest - marked.of(entry).deepest, without.of(entry).at_a_trap - marked.of(entry).at_a_trap)
    assert bought == BOUGHT, f"the marks buy {bought} bytes of the two bounds: say why it moved"
    read = {function: (_frames(without, function), _frames(marked, function)) for function in sorted(MARKS)}
    assert read == BOUGHT_BY_FUNCTION, f"the marked functions' frames, without and with: {read}"
    for function, (off, on) in read.items():
        pairs = [(before, after) for before, after in zip(off, on) if before is not None and after is not None]
        assert all(after <= before for before, after in pairs) and any(after < before for before, after in pairs), (
            f"{function}: its mark buys it nothing, or costs it stack ({off} without, {on} with)")
