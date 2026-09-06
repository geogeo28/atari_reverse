"""The IMAGE MODEL: that `../bin/GHOST_RT.PRG` plus the post-init fixture is the machine the real
crt0 builds, and that the harness's fixed regions do not sit on top of it.

Nothing else in this project can be trusted until this file is green, because every differential
case is staged on that image and passes `a4 = A4_BASE`. Both halves of the claim are checked:

* **the relayout** — `tools/prg_relayout.py` moved the DATA segment above the BSS to produce
  GHOST_RT.PRG, so its TEXT and DATA bytes must be GHOST_PLAIN.PRG's, byte for byte, and the gap
  between them must be zero (the BSS the crt0 clears);
* **the startup** — running the program's OWN crt0 (`crt0_start` @ 0x10036) on a FILE-layout image
  with a fabricated basepage, to the instruction before it calls `main`, must produce the same
  memory as GHOST_RT.PRG loaded plus `conftest.py`'s `post_init_image` fixture. That is the whole
  argument for the fixture: it is not a convention this suite invented, it is what the program does.

IT HAS ALREADY EARNED ITS KEEP. The crt0 comparison is what found that `init_globals` reads A5 —
its last paragraph builds a seven-entry pointer table with `lea n(a5),a0` — which no reading of the
routine's prologue would have suggested and which a fixture entered with A5 = 0 gets silently
wrong, in seven longwords of live game state. See `conftest.py`, `INIT_GLOBALS_A5`.

The census at the bottom is the other half: that none of the kit's fixed regions collides with this
program. The Malloc arena is the one that would, at the kit's default base — `project.toml` moves it
with `heap_base`, and the two cases here assert both that the moved arena is clear of everything and
that a served `Malloc` really lands there on both sides.
"""
import ctypes
import struct
import sys

import pytest

import abi
import conftest
import emu
import harness
import loader
from recreate_kit import project as kit_project   # harness's import put reverse/tools on sys.path
from recreate_kit import stubs
from test_constants import check_entry_prologues, check_mirrors

# ---- what the two .PRG headers say, read rather than restated ------------------------------------
PLAIN_PRG = harness.PRG.parent / "GHOST_PLAIN.PRG"    # the decrypted FILE layout: [TEXT][DATA][BSS]
RT_PRG = harness.PRG                                  # project.toml's: [TEXT][BSS][DATA]


@pytest.fixture(autouse=True)
def _leave_the_loader_bound_to_the_run_time_prg():
    """Two cases here `loader.load_image(PLAIN_PRG)`, which REBINDS the loader's module-level
    geometry (`PROGRAM_END` and friends) for the rest of this xdist worker's session.

    It is harmless for the value both layouts agree on — which is the very thing one of those cases
    asserts — but it is a global left changed by a test, and the next file to run on this worker
    (`test_constants.py::test_every_named_address_is_inside_the_program` reads `loader.PROGRAM_END`)
    would be checking a binding this module chose. So every case here puts the run-time .PRG back.
    """
    yield
    loader.load_image(RT_PRG)

# `include/globals.h`'s memory model, mirrored here. MIRRORS at the bottom pins each one equal.
BG_LOAD_BASE = 0x10000
BG_TEXT_BYTES = 0xe8ca
BG_DATA_BYTES = 0x2f4
BG_BSS_BYTES = 0x6650
BG_BSS_BASE = 0x1e8ca
A4_BASE = 0x24f1a
BG_PROGRAM_END = 0x2520e
BG_STACK_TOP = 0x2720e
BG_BASEPAGE_BYTES = 0x100
BG_CRT0_STACK_SLACK = 0x2100     # what the crt0 Mshrinks to above the program (@ 0x10048); its one
                                 # reader is the derivation of BG_STACK_TOP below

# The three entry points this file drives, with the bytes each really starts with (read off the
# loaded image). A mistyped entry would run a different routine and could still come back clean.
ENTRY_CRT0 = 0x10036             # `movea.l a7,a5` — the crt0, reached from the jump table @ 0x10000
ENTRY_INIT_GLOBALS = 0x16d8e     # `lea -7308(a4),a1` — conftest's fixture builder
ENTRY_MAIN = 0x100dc             # `link a6,#$0` — what the crt0 calls last
# The crt0's `jsr $100dc(pc)` — the checkpoint. Stopping HERE rather than at `main`'s first
# instruction is what keeps the comparison about the startup: the argc/argv words are already
# pushed and nothing of the game has run.
CRT0_BEFORE_MAIN = 0x100c0
CRT0_MAX_INSNS = 200_000         # the BSS clear alone is 0x6650 iterations; measured 61,806

# ---- the Malloc arena `project.toml` places (see the census below) -------------------------------
BG_HEAP_BASE = 0x30000           # project.toml's `heap_base`; pinned against the bound config below
BG_HEAP_LIMIT = 0x90000          # ...and its `heap_limit`: the first address the arena may not
                                 # reach, which is abi.STUB — the arena and the scratch map share
                                 # this boundary, so it is asserted equal below rather than twice

# WHAT THIS GAME ALLOCATES, one call at a time — (what, calls, bytes each), read off the asm rather
# than restated from prose. Every existing count in this project was wrong before it was derived
# here: the sizes came from `../notes/anchors.md`'s "Files", and the CALL counts from the nine
# `jsr $15b54` (`c_malloc`) sites, two of which are loops.
#
# The palette allocations are the trap: `load_level_pictures` takes ONE 0x20 palette after its
# six-iteration picture loop (0x139d0), not one per picture — the old `6*(0x7800+0x20)` breakdown
# counted five palettes that do not exist and put this constant 0xa0 bytes high.
BG_MALLOC_REQUESTS = (
    ("GHOST.VOI  load_voice_player @ 0x13c6c",            1, 0x7594),
    ("GHOST.PRE  load_presentation @ 0x10e44",            1, 0x7800),
    ("GHOST.PRE  ...its palette, @ 0x10e82",              1, 0x0020),
    ("GHOST.DAT  load_level_pictures @ 0x1396c, x6 loop", 6, 0x7800),
    ("GHOST.DAT  ...its palette, ONCE @ 0x139d0",         1, 0x0020),
    ("GHOST.DEM  load_demo @ 0x10dea",                    1, 0x1770),
)
BG_MALLOC_CALLS = sum(calls for _what, calls, _size in BG_MALLOC_REQUESTS)
BG_HEAP_BYTES_ASKED = sum(calls * size for _what, calls, size in BG_MALLOC_REQUESTS)

# ...and the OTHER claim on the same arena, on the same boot path: `build_sprite_bank` @ 0x132ec
# loads no file but takes 60 tiles plus two background patches of 0x200 each (0x13338 in a
# 60-iteration loop, then 0x1340e and 0x1341c). It is counted in the headroom below because the
# model's Malloc never frees, so every request on the path is cumulative.
BG_SPRITE_BANK_BYTES = 62 * 0x200

# The oracle side of that census: `Malloc(-1)`, the "largest free block?" query. It is poked at
# abi.STUB rather than found in the program because the game reaches Malloc only through its C
# library's allocator, several frames down a path this project cannot yet run.
MALLOC_LARGEST_FREE_STUB = stubs.gemdos_malloc_stub(stubs.MALLOC_LARGEST_FREE)

# A stub that reads back what `abi.stack_args` pushed: `move.w 4(a7),d0 / move.l 6(a7),d1 / rts`.
# `emu.run` forces A7 to STACK_TOP and writes the sentinel return address there, so 4(a7) is
# abi.FIRST_ARG — exactly where the callee of a `jsr` finds its first argument.
STACK_ARGS_PROBE = bytes.fromhex("302f0004" "222f0006" "4e75")

# GEMDOS basepage field offsets (the eight longwords the crt0 reads).
BP_LOWTPA, BP_HITPA = 0, 4
BP_TBASE, BP_TLEN = 8, 12
BP_DBASE, BP_DLEN = 16, 20
BP_BBASE, BP_BLEN = 24, 28

# Where the crt0 puts the basepage pointer: `move.l a5,-4(a4)` @ 0x1009e. It is the one byte of the
# program the crt0 writes and `init_globals` does not, so it is the one documented difference
# between the two sides of the equivalence below.
BASEPAGE_SLOT = A4_BASE - 4


def _prg(path):
    """(header, image bytes) for one .PRG — its TEXT+DATA exactly as the loader copies them."""
    data = path.read_bytes()
    head = loader.prg_dis.parse_header(data)
    return head, data[loader.HEADER:loader.HEADER + head["tlen"] + head["dlen"]]


# ==================================================== the relayout


def test_the_relayout_kept_every_text_byte():
    """GHOST_RT.PRG's TEXT must open with GHOST_PLAIN.PRG's, unchanged.

    `prg_relayout.py` folds the BSS into text (text' = tlen + blen), so the ORIGINAL text is the
    first `tlen` bytes of the new one. All nine relocations sit in the jump table at TEXT+0 and all
    nine target TEXT, so not one of them was retargeted — which is why this is a plain equality and
    not an equality-with-exceptions.
    """
    plain_head, plain = _prg(PLAIN_PRG)
    rt_head, rt = _prg(RT_PRG)
    assert rt_head["tlen"] == plain_head["tlen"] + plain_head["blen"]
    assert rt[:plain_head["tlen"]] == plain[:plain_head["tlen"]]


def test_the_relayout_kept_every_data_byte():
    """...and its DATA must be GHOST_PLAIN.PRG's DATA, moved up by exactly the BSS length."""
    plain_head, plain = _prg(PLAIN_PRG)
    rt_head, rt = _prg(RT_PRG)
    assert rt_head["dlen"] == plain_head["dlen"] == BG_DATA_BYTES
    assert rt[rt_head["tlen"]:] == plain[plain_head["tlen"]:plain_head["tlen"] + plain_head["dlen"]]


def test_the_relayout_left_the_bss_gap_zero():
    """The bytes between them are the BSS, which the crt0 clears — so the image must hold zeroes.

    Without this the two tests above would still pass over an image carrying the FILE layout's DATA
    in the middle of the BSS, which is the exact mistake the relayout exists to undo.
    """
    plain_head, _plain = _prg(PLAIN_PRG)
    _rt_head, rt = _prg(RT_PRG)
    gap = rt[plain_head["tlen"]:plain_head["tlen"] + plain_head["blen"]]
    assert len(gap) == BG_BSS_BYTES and not any(gap)


def test_a4_is_the_bss_data_boundary_in_both_headers():
    """`a4` derived from each .PRG's own header, two different ways, must be the one A4_BASE.

    File layout: a4 = p_dbase + p_blen = (load_base + tlen) + blen, which is what the crt0 computes
    (`movea.l 16(a5),a4 / adda.l 28(a5),a4` @ 0x10096). Run-time layout: a4 = load_base + tlen',
    since the relayout folded the BSS into text. They are the same number or the relayout is wrong.
    """
    plain_head, _ = _prg(PLAIN_PRG)
    rt_head, _ = _prg(RT_PRG)
    assert BG_LOAD_BASE + plain_head["tlen"] + plain_head["blen"] == A4_BASE
    assert BG_LOAD_BASE + rt_head["tlen"] == A4_BASE
    assert abi.A4_BASE == A4_BASE, "test/abi.py's A4_BASE is what every case passes in `regs`"


def test_both_layouts_load_to_the_same_program_end():
    """`loader.PROGRAM_END` must not depend on which of the two .PRGs was loaded.

    The crt0 comparison below loads the FILE layout into the same process, which REBINDS this
    module-level value. It is harmless only because the two agree — text+data+bss is the same
    program either way — and that is a fact worth holding rather than assuming.
    """
    end_of_rt = loader.PROGRAM_END
    loader.load_image(PLAIN_PRG)
    assert loader.PROGRAM_END == end_of_rt == BG_PROGRAM_END


# ==================================================== the startup


def _file_layout_image_with_a_basepage():
    """A FILE-layout image of GHOST_PLAIN.PRG staged as TOS would hand it to the crt0.

    TOS puts the 256-byte basepage immediately below the text segment and passes a pointer to it at
    4(A7) — the same place a `jsr` from GEMDOS would leave it, which is `abi.FIRST_ARG` (`emu.run`
    forces A7 to STACK_TOP and writes the sentinel return address there, so the first argument sits
    one longword above). Spelt through `abi` rather than re-derived, so this and `abi.stack_args`
    cannot disagree about where a callee looks.
    """
    image = loader.load_image(PLAIN_PRG)
    basepage = BG_LOAD_BASE - BG_BASEPAGE_BYTES
    fields = bytearray(BG_BASEPAGE_BYTES)
    struct.pack_into(">I", fields, BP_LOWTPA, basepage)
    struct.pack_into(">I", fields, BP_HITPA, loader.IMAGE_SIZE)
    struct.pack_into(">I", fields, BP_TBASE, BG_LOAD_BASE)
    struct.pack_into(">I", fields, BP_TLEN, BG_TEXT_BYTES)
    struct.pack_into(">I", fields, BP_DBASE, BG_LOAD_BASE + BG_TEXT_BYTES)
    struct.pack_into(">I", fields, BP_DLEN, BG_DATA_BYTES)
    struct.pack_into(">I", fields, BP_BBASE, BG_LOAD_BASE + BG_TEXT_BYTES + BG_DATA_BYTES)
    struct.pack_into(">I", fields, BP_BLEN, BG_BSS_BYTES)
    image[basepage:basepage + BG_BASEPAGE_BYTES] = fields
    struct.pack_into(">I", image, abi.FIRST_ARG, basepage)
    return image, basepage


@pytest.fixture(scope="module")
def crt0_run():
    """(image, registers) at the instruction before the crt0 calls `main`."""
    image, basepage = _file_layout_image_with_a_basepage()
    final, _writes, regs = emu.run(image, ENTRY_CRT0, stop_pc=CRT0_BEFORE_MAIN,
                                   max_insns=CRT0_MAX_INSNS)
    return final, regs, basepage


def test_the_crt0_establishes_a4_and_the_games_stack(crt0_run):
    """A4 and A7 at the checkpoint are the memory model `include/globals.h` states."""
    _final, regs, _basepage = crt0_run
    assert regs["a4"] == A4_BASE
    assert regs["a5"] == BG_LOAD_BASE, "a5 = p_tbase, which init_globals reads (see conftest.py)"
    # A7 itself is not reported (it is the harness's), but `min_a7` is — and the crt0 pushes
    # argc/argv and the Mshrink frame, so the deepest it reached must sit just under the top.
    assert BG_STACK_TOP - 0x20 <= regs["min_a7"] < BG_STACK_TOP
    # ...and the top itself is basepage + text + data + bss + the crt0's slack, word-aligned down.
    # Derived rather than asserted as a literal, so BG_CRT0_STACK_SLACK has a reader that would
    # notice it changing (globals.h states it; nothing else in this project reads it).
    assert BG_STACK_TOP == (BG_PROGRAM_END - BG_BASEPAGE_BYTES + BG_CRT0_STACK_SLACK) & ~1


def test_the_crt0_produces_the_post_init_image(crt0_run, post_init_image):
    """THE PIN: the real startup's memory == GHOST_RT.PRG loaded + `init_globals` run.

    Compared over the whole program, [load_base, PROGRAM_END) — TEXT, BSS and DATA alike, so the
    segment move, the BSS clear and every one of `init_globals`' ~15,700 written bytes are all in
    scope. Exactly one byte may differ, and it is named rather than excluded: the crt0 stores the
    basepage pointer at -4(a4) and `init_globals` does not, so the fixture holds zero there.
    """
    final, _regs, basepage = crt0_run
    ours = bytearray(final[BG_LOAD_BASE:BG_PROGRAM_END])
    fixture = bytearray(post_init_image[BG_LOAD_BASE:BG_PROGRAM_END])
    # The one permitted difference, checked on both sides and then blanked on both — rather than
    # walked around — so the rest is a single `bytes ==`. A byte-by-byte walk over the whole program
    # is the slowest thing in this file and it runs on every green pass to produce a list that is
    # only ever read when it is non-empty; the walk below happens only when there IS a mismatch.
    slot = BASEPAGE_SLOT - BG_LOAD_BASE
    assert int.from_bytes(ours[slot:slot + 4], "big") == basepage
    assert int.from_bytes(fixture[slot:slot + 4], "big") == 0
    ours[slot:slot + 4] = fixture[slot:slot + 4] = bytes(4)
    if bytes(ours) != bytes(fixture):
        differing = [BG_LOAD_BASE + i for i in range(len(ours)) if ours[i] != fixture[i]]
        raise AssertionError(
            f"the crt0's memory and the post-init fixture differ at {len(differing)} byte(s), the "
            f"first at {differing[0]:#x} — the fixture is not what the program's own startup builds")


def test_the_fixture_is_not_the_bare_image(post_init_image):
    """The positive control: `init_globals` really did write, and into the BSS.

    Every assertion above is an equality between two things this file builds, so a fixture that
    silently ran nothing at all would satisfy them by agreeing with a crt0 whose `jsr 48(a5)` had
    also gone nowhere.
    """
    base = bytes(harness.BASE_IMAGE)
    changed = [i for i in range(BG_LOAD_BASE, BG_PROGRAM_END) if post_init_image[i] != base[i]]
    # Measured 7,056 CHANGED bytes out of 15,693 written — about half of what the routine stores is
    # a zero over the zero the loaded BSS already holds. The bar is on the changed count, since that
    # is what a case can actually observe, and is set low enough not to be a tuning knob.
    assert len(changed) > 5_000, f"init_globals changed only {len(changed)} bytes"
    assert BG_BSS_BASE <= min(changed) and max(changed) < A4_BASE, (
        "init_globals wrote outside the BSS, which nothing in ../notes/anchors.md describes")


# ==================================================== the free-space census


def test_the_malloc_arena_holds_what_this_game_asks_for():
    """THE ONE COLLISION, MOVED — `project.toml`'s `heap_base` rather than a waiver.

    The kit's default arena (`OS_HEAP_BASE_DEFAULT` = 0x20000) lands in the middle of this program's
    BSS, and Bubble Ghost DOES issue GEMDOS Malloc, so `tos_malloc_unused` — the claim that a game
    never allocates — would simply be false here.

    NOTHING HERE RESTATES WHAT THE KIT ALREADY REFUSES. `harness._vet_os_memory_map` runs at import
    and will not let this suite start at all if the arena sits inside the program, over the
    staged-file table, on the poked block or in the framebuffer; the file table's and the poked
    block's own clearances are refused there too. What is left is what only THIS project knows: the
    base it chose, the number of bytes its game asks for, and that the window is wide enough for
    them.
    """
    assert emu.OS_HEAP_BASE == BG_HEAP_BASE, (
        f"project.toml's heap_base is no longer {BG_HEAP_BASE:#x}; this census is about that value")
    assert emu.HEAP_LIMIT == BG_HEAP_LIMIT == abi.STUB, (
        "the arena's ceiling and the scratch map's floor are one boundary: project.toml's "
        "`heap_limit` must stay equal to test/abi.py's STUB")
    assert emu.OS_HEAP_BASE + BG_HEAP_BYTES_ASKED + BG_SPRITE_BANK_BYTES <= emu.HEAP_LIMIT, (
        f"the {BG_HEAP_BYTES_ASKED + BG_SPRITE_BANK_BYTES:#x} bytes this game asks for on its boot "
        f"path reach past the arena's {emu.HEAP_LIMIT:#x} ceiling")
    assert kit_project.current().tos_malloc_unused is False, (
        "the waiver is gone: this project moves the arena rather than claiming it never allocates")


def test_the_derived_malloc_census_is_the_one_the_prose_quotes():
    """The census is SUMMED from its own breakdown, so the two cannot disagree — but the numbers
    the docs quote are still hand-copied, and this is where they are read back from.

    `project.toml`, `README.md` and `STATUS.md` all quote a call count and a size; every one of them
    was wrong before this was derived (seven calls and 0x3d5e4 bytes, against eleven and 0x3d544).
    """
    assert BG_MALLOC_CALLS == 11, "the four file loaders make eleven `jsr $15b54` calls, not seven"
    assert BG_HEAP_BYTES_ASKED == 0x3d544, (
        f"the breakdown sums to {BG_HEAP_BYTES_ASKED:#x}; the docs quote 0x3d544 (245 KiB)")
    assert BG_SPRITE_BANK_BYTES == 0x7c00


def test_the_project_shim_still_carries_the_kits_heap_base():
    """`test/harness.py` is `from recreate_kit.harness import *`, and the kit now SERVES
    `OS_HEAP_BASE` from a module `__getattr__` rather than storing it — so it reaches a shim only
    because the kit lists it in `__all__`. A battery may read either spelling; both must be here.
    """
    assert harness.OS_HEAP_BASE == emu.OS_HEAP_BASE == BG_HEAP_BASE


def test_the_arena_and_the_scratch_map_do_not_overlap():
    """The two claims on the free window meet at abi.STUB, and neither may cross it.

    Asserted because they are configured in different files — `heap_limit` in project.toml, the map
    in test/abi.py — so nothing but this notices one of them moving.
    """
    assert BG_PROGRAM_END <= emu.OS_HEAP_BASE < emu.HEAP_LIMIT <= abi.STUB


def test_a_served_malloc_lands_at_the_configured_base_on_both_sides():
    """The key is only real if BOTH sides follow it, and only asking each of them can say so.

    The ORACLE is asked with the .PRG's own idiom: `Malloc(-1)`, GEMDOS's "how big is the largest
    free block?" query, which the model serves fully and which rounds to a zero-size bump — so it
    reports the arena's base without moving the pointer. The CANDIDATE is asked for `OS_HEAP_BASE`
    itself, which is now a variable the kit installs (`g_os_heap_base`, `src/os_heap.c`): every
    reconstruction that mirrors an allocation reads exactly this, so a `.so` left at the kit default
    while the oracle allocated from 0x30000 would be wrong by a whole arena, silently.
    """
    _, _, out_regs = emu.run(harness.make_image({abi.STUB: MALLOC_LARGEST_FREE_STUB}), abi.STUB, {})
    assert out_regs["d0"] == BG_HEAP_BASE, "the oracle's Malloc did not come from `heap_base`"
    assert out_regs["heap"] == BG_HEAP_BASE, "Malloc(-1) must not move the bump pointer"

    candidate_base = ctypes.c_uint32.in_dll(harness._lib, "g_os_heap_base").value
    assert candidate_base == BG_HEAP_BASE, (
        f"the candidate reads OS_HEAP_BASE as {candidate_base:#x} while the oracle allocates from "
        f"{BG_HEAP_BASE:#x} — the two sides are using different arenas")


def test_the_scratch_map_is_free_space():
    """`test/abi.py` parks its stub and buffers above the program and below the staged-file table.

    Unlike Zynaps there is no framebuffer hole to dodge: this game asks XBIOS for its screen
    (`video_init` @ 0x10118 takes Logbase and its back buffer 0x7d00 below it), which the model
    answers with OS_SCREEN_BASE, far below load_base. What the map must leave whole instead is the
    Malloc arena below it — see abi.py, and the two cases above.
    """
    top = abi.SCRATCH + abi.SCRATCH_BYTES
    for name in ("STUB", "RESULT", "SCRATCH"):
        assert getattr(abi, name) >= BG_PROGRAM_END, f"abi.{name} is inside the program"
    assert abi.STUB < abi.RESULT < abi.SCRATCH < top
    assert top <= harness.OS_FS_TABLE, (
        f"the scratch map reaches {top:#x}, at or past the staged-file table "
        f"{harness.OS_FS_TABLE:#x}")


# ==================================================== the calling convention


def test_stack_args_puts_arguments_where_an_alcyon_c_routine_reads_them():
    """`abi.stack_args` had no caller at all, so its offsets and its widths were unverified.

    The probe reads 4(a7) as a word and 6(a7) as a longword — where `link a6,#-n` then finds 8(a6)
    and 10(a6) — and reports them in registers, which is the only surface for values the routine
    does not store. The word argument is NEGATIVE on purpose: a C routine taking a `short` is the
    common case for one, and it is the two's-complement word the compiler would have pushed.
    """
    word, longword = -2, 0x12345678
    pokes = {abi.STUB: STACK_ARGS_PROBE, **abi.stack_args((2, word), (4, longword))}
    _final, _writes, out_regs = emu.run(harness.make_image(pokes), abi.STUB, {})
    assert out_regs["d0"] & 0xffff == word & 0xffff
    assert out_regs["d1"] == longword


@pytest.mark.parametrize("width, value", ((2, 1 << 16), (2, -(1 << 15) - 1), (4, 1 << 32)))
def test_stack_args_refuses_a_value_the_width_cannot_carry(width, value):
    """...and says so in terms of SIGNEDNESS, since accepting a negative is the whole change: a
    message about the width alone would read as a bug report against the caller's own arithmetic."""
    with pytest.raises(AssertionError, match="signed"):
        abi.stack_args((width, value))


# ==================================================== the fixture's own cost


def test_the_post_init_run_is_the_length_conftest_states():
    """`conftest.py` states the fixture's cost in one place and this is what keeps it true.

    It carried two numbers before — a docstring's "~4,700 instructions" and a comment's measured
    7,871 — with nothing to say which was the run's, so both were quotable and one was wrong.
    """
    _image, _writes, regs = emu.run(harness.BASE_IMAGE, conftest.INIT_GLOBALS,
                                    regs={"a4": abi.A4_BASE, "a5": conftest.INIT_GLOBALS_A5},
                                    max_insns=conftest.INIT_GLOBALS_MAX_INSNS)
    assert regs["ninsns"] == conftest.INIT_GLOBALS_INSNS


def test_every_differential_starts_from_the_post_init_image(post_init_image):
    """The autouse fixture's own surface: `harness.make_image()` must be the post-init image.

    Without it a battery that forgot to stage its case would run against a bss of ZEROES and go
    green about a machine that never exists at run time — which is exactly the failure the fixture
    exists to make unforgettable, and which nothing else here would notice.
    """
    assert bytes(harness.make_image()) == post_init_image
    assert bytes(harness.make_image()) != bytes(harness.BASE_IMAGE)


# ==================================================== the pins this file declares
#
# Shaped like a battery's (README.md, "Adding a function") even though this is not one — there is no
# `src/image_model.c`, so `test_constants.py` does not discover it and these are checked here.

MIRRORS = (
    ("BG_LOAD_BASE", "include/globals.h", "BG_LOAD_BASE"),
    ("BG_TEXT_BYTES", "include/globals.h", "BG_TEXT_BYTES"),
    ("BG_DATA_BYTES", "include/globals.h", "BG_DATA_BYTES"),
    ("BG_BSS_BYTES", "include/globals.h", "BG_BSS_BYTES"),
    ("BG_BSS_BASE", "include/globals.h", "BG_BSS_BASE"),
    ("A4_BASE", "include/globals.h", "A4_BASE"),
    ("BG_PROGRAM_END", "include/globals.h", "BG_PROGRAM_END"),
    ("BG_STACK_TOP", "include/globals.h", "BG_STACK_TOP"),
    ("BG_BASEPAGE_BYTES", "include/globals.h", "BG_BASEPAGE_BYTES"),
    ("BG_CRT0_STACK_SLACK", "include/globals.h", "BG_CRT0_STACK_SLACK"),
)

ENTRY_PROLOGUES = {
    "ENTRY_CRT0": "2a4f2a6d0004202d",          # movea.l a7,a5 / movea.l 4(a5),a5 / move.l 12(a5),d0
    "ENTRY_INIT_GLOBALS": "43ece37432fc001e",  # lea -7308(a4),a1 / move.w #$1e,(a1)+
    "ENTRY_MAIN": "4e5600003f3c0004",          # link a6,#$0 / move.w #$4,-(a7)  (Getrez)
}


def test_this_files_constants_mirror_the_header():
    """CLAUDE.md §5: one canonical definition, the copy pinned equal by a test.

    `test_constants.py`'s own checker, called on this module — the loop was written out here as
    well until the two copies were free to drift.
    """
    check_mirrors(sys.modules[__name__])


def test_the_entry_addresses_still_point_at_their_routines():
    """Pinned against the ORIGINAL's own bytes, so the check needs nothing but the loaded .PRG."""
    check_entry_prologues(sys.modules[__name__])
