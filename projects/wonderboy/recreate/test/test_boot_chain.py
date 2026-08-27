"""THE BOOT CHAIN COMPOSED, differentially: the four slices between the boot's fire waits.

test_boot.py verifies the boot's routines ONE AT A TIME — the block movers, the two installers, the
load path, the dispatcher's three pieces. Every one of them is green and none of them says what the
boot DOES with them. This battery is the other half: src/boot.c's `boot_title_screen`,
`boot_credits_screen`, `boot_load_stage` and `boot_prompt_screen` are the runs of those calls in the
boot's own order with the boot's own operands, and each case here enters the ORACLE at that slice's
first instruction, runs it to the instruction the slice ends at, and requires the whole image to
agree. The fourth is the ESC ending's — `show_data_disk_prompt` at $e494, which no run of the other
three reaches — and it is here because it is cut by a wait of the same shape and is composed of the
same calls.

WHY THESE CUTS AND WHY THERE. $e4e6's continuation breaks three times for a FIRE WAIT — `clr.b
WB_JOY1_STATE`, then two `tst.b` spins on a byte only the IKBD interrupt writes. A spin on a byte no
instruction of the run stores is the shim's and the schedule model's business, not C's, so the waits
are the boundaries and each slice runs from one to the next. WB_BOOT_*_AT / _END in
include/wonderboy.h are those addresses and this file asserts the instruction bytes at every one of
them, so a wrong constant fails HERE and not as a puzzling diff a megabyte away.

WHAT THESE PIN THAT THE LEAF CASES CANNOT
  * the ORDER, where memory can see it: that the resource table is parked before the overlay depack
    and put back after it, and that the tile bank is installed before SPRITES.CRU lands on top of it.
    NOT the credits slice's own last two steps — see the survivor below;
  * the OPERANDS: which resource index goes to which destination, and which of the two screen
    buffers each picture inflates into;
  * the ARMS: that the second load runs on a first entry to a stage and does NOT run on a re-entry,
    over both the shipped row that carries a zero in its second-load byte and the re-entry the
    dispatcher produces from WB_LIFE_RESTART_ENTRY_C26;
  * the STOPS: that a load the seam refuses ends the slice where the original starts waiting for
    fire, rather than inflating a buffer the file never arrived in.

THE ONE BAND EVERY CASE HANDS THE CANDIDATE, and it is not part of any of this. `rad_depack`'s first
instruction is `move.l a7,WB_RAD_SAVED_SP`: it parks its CALLER's stack pointer so its own exit can
restore it, and a C composition has no such register — the same hole src/rad.c's `g_rad_depack` glue
fills one level down. The kit REFUSES to drop the band from the diff (harness._vet_exclude_bands: it
lies far below any stack the run touches, so excluding it could hide real output), which is right, so
the value is handed to the candidate instead and the byte-for-byte diff still covers the write. See
`_park_saved_sp` for why the value is derived rather than assumed.

KNOWINGLY NOT PINNED
  * THE CREDITS SLICE'S PEN. `move.w #$77,$ff8254.l` raises one shifter colour register, and
    WB_SHIFTER_PALETTE is off the loaded image, so the oracle drops the write and the port's own
    sink compiles to nothing off target. Deleting that line is invisible to every case in this file
    — measured, not assumed: it is a SURVIVING mutant in ../STATUS.md's batch 44 phase C table. It
    is the same hole `set_palette` and `clear_palette` have carried since batch 12, waiting on the
    same kit-side remedy (a dropped-hardware-write ledger), and the on-target rung is what will see
    it instead. WHAT IS PINNED is which register and which colour: both are decoded out of the
    shipped instruction at $e5a2 (see the two operand cases below), so the write's IDENTITY cannot
    drift even while its HAPPENING stays unobservable.
  * THE SPRITE PRODUCT ON THE ARMED ARM. SPRITES.CRU is larger than the whole staging area the kit's
    file model has to lay files in (test_boot.py measures that), so the armed arm is driven over the
    PREFIX of the shipped file that fits. Both cores read identical bytes, so what that case pins is
    the CHAIN — that the arm is taken, with that index, to that destination, and that the installer
    runs inside it. The installer's product over the WHOLE file is test_boot.py's, which pokes the
    279,034 bytes straight into the image and never goes through the seam.
  * A WRITE-SET MODEL FOR THE CREDITS AND STAGE SLICES. Their write sets are the union of eight
    routines' own, each already stated by the battery that owns it (test_stage.py, test_sound.py,
    test_boot.py). A second model here would be a contract nothing enforced and free to be wrong, so
    those two carry a BOUND instead — `_boot_owned_bands` — and say so. The title slice's three
    callees ARE enumerable and it states its bands exactly.
"""
import ctypes
import functools

import pytest

import copylock
import emu
import harness
import leaf
from layout import wb

from test_boot import (ACTOR_TABLES, ACTOR_TABLE_SPAN, BIN, COPYLOCK_ARM_FLAG,
                       COPYLOCK_ARM_FLAG_LEN, DISK2, FLOPPY_IDLE_TIMER, LEVEL_SEQ_INDEX,
                       LEVEL_SEQ_SECOND_LOAD,
                       LIFE_RESTART_ENTRY_C26, LOAD_COPYLOCK_RAN, LOAD_DISK_ERROR, LOAD_OK,
                       LOAD_RETRY_DEST, LOAD_RETRY_INDEX, LONGWORD_LEN, POISON,
                       RESOURCE_LOAD_BUFFER, SCREEN_BYTES, SCREEN_HIGH, SCREEN_LOW, WORD_LEN,
                       STAGING_CAPACITY, _row_of, seam_pokes)
from test_sound import PLAY_SONG_MIXER, PLAY_SONG_SEEDED_BANDS, PSG_REG_MIXER, model_play_song
# `game_restart_reset`'s own seeding, so the credits slice's reset is ATTRIBUTABLE — see
# `_credits_pokes`. Imported rather than restated for `model_play_song`'s reason.
from test_stage import LIVES_ON_RESTART, _reset_pokes

import depack_rad                                              # noqa: E402  (harness put tools/ on
                                                               #              sys.path)

# --- the cuts, and what has to be at them ---------------------------------------------------------
TITLE_AT = wb("BOOT_TITLE_AT")
TITLE_SONG_AT = wb("BOOT_TITLE_SONG_AT")
TITLE_END = wb("BOOT_TITLE_END")
CREDITS_AT = wb("BOOT_CREDITS_AT")
CREDITS_PEN_AT = wb("BOOT_CREDITS_PEN_AT")
CREDITS_END = wb("BOOT_CREDITS_END")
PROMPT_AT = wb("BOOT_PROMPT_AT")
PROMPT_PALETTE_AT = wb("BOOT_PROMPT_PALETTE_AT")
PROMPT_END = wb("BOOT_PROMPT_END")
PROMPT_BASE_HI_AT = wb("BOOT_PROMPT_BASE_HI_AT")
PROMPT_BASE_MID_AT = wb("BOOT_PROMPT_BASE_MID_AT")
STAGE_AT = wb("BOOT_STAGE_AT")
STAGE_SPRITES_AT = wb("BOOT_STAGE_SPRITES_AT")
STAGE_JMP_AT = wb("BOOT_STAGE_JMP_AT")
STAGE_END = leaf.entry_of("game_main_loop")     # `jmp $4a0.w` — where the slice hands over

TITLE_DEPACK_DEST = wb("TITLE_DEPACK_DEST")
TITLE_SONG = wb("TITLE_SONG")
CREDITS_DEPACK_DEST = wb("CREDITS_DEPACK_DEST")
# NOT scraped, and there is nothing left here to scrape: since the review gate, the header DERIVES
# WB_TITLE_PALETTE_SRC / WB_CREDITS_PALETTE_SRC as `dest + WB_RAD_PICTURE_PALETTE_OFF` rather than
# spelling a second literal, and layout.py reads plain literals only. So the palette row is one
# definition in C and this file has no independent value to cross-pin it against. What the picture
# case below states instead is the offset's own claim — that the row lies INSIDE the prefix, so the
# palette words are not part of the picture; and what pins the destinations themselves is the
# differential (depacking two bytes high is a caught mutant, ../STATUS.md §4's T2 and S4).
# ...and the same holds for the PROMPT slice's three operands: WB_PROMPT_SCREEN_BASE,
# WB_PROMPT_DEPACK_DEST and WB_PROMPT_PALETTE_SRC are all DERIVED #defines (WB_SCREEN_HIGH and the
# credits pair, because the prompt inflates the same shape into the same buffer), so layout.py
# cannot scrape them and this file has no independent value to cross-pin them against. What it
# states instead is the claim each derivation rests on: the picture case below says the geometry
# holds for DATADISK.RAD, and the base case says the two shipped `move.b` immediates really do
# compose SCREEN_HIGH.
PICTURE_PALETTE_OFF = wb("RAD_PICTURE_PALETTE_OFF")
PICTURE_PREFIX = wb("RAD_PICTURE_PREFIX")
RAD_SAVED_SP = wb("RAD_SAVED_SP")
RAD_SAVED_SP_LEN = wb("RAD_SAVED_SP_LEN")

# The two operands the composed slices carry that NO differential can see (a song id the sound model
# swallows, a colour register off the loaded image), pinned against the original's own instruction
# bytes below.
TITLE_SONG_ID_AT = wb("BOOT_TITLE_SONG_ID_AT")
CREDITS_PROMPT_PEN = wb("CREDITS_PROMPT_PEN")
CREDITS_PROMPT_COLOUR = wb("CREDITS_PROMPT_COLOUR")
SHIFTER_PALETTE = wb("SHIFTER_PALETTE")
# WB_SHIFTER_PALETTE_STRIDE is itself a derived #define, so layout.py cannot scrape it; its two
# literal parts are what the header divides, and test_boot.py/test_stage.py spell it the same way.
PALETTE_STRIDE = wb("PALETTE_ROW_BYTES") // wb("PALETTE_COLOURS")

# Each cut's own instruction, read out of the loaded image. Same discipline as test_boot.py's
# ENTRY_INSNS: a constant that drifted fails at collection instead of inside a two-million-
# instruction run.
CUT_INSNS = {
    PROMPT_AT: b"\x61\x00\x03\x5e",                       # bsr.w $e7f4       (clear_palette)
    PROMPT_PALETTE_AT: b"\x4e\xb9\x00\x00\xf9\x44",        # jsr $f944.l       (set_palette)
    PROMPT_END: b"\x42\x38\x08\x77",                      # clr.b $877.w      (the fourth wait)
    TITLE_AT: b"\x20\x3c\x00\x00\x00\x00",              # move.l #$0,d0     (WB_RESOURCE_TITLESCR)
    TITLE_SONG_AT: b"\x4e\x90",                         # jsr (a0)          (the sound module)
    TITLE_END: b"\x42\x38\x08\x77",                     # clr.b $877.w      (the fire wait)
    CREDITS_AT: b"\x20\x3c\x00\x00\x00\x01",            # move.l #$1,d0     (WB_RESOURCE_CREDITS)
    CREDITS_PEN_AT: b"\x33\xfc\x00\x77\x00\xff\x82\x54",  # move.w #$77,$ff8254.l
    CREDITS_END: b"\x42\x38\x08\x77",                   # clr.b $877.w
    STAGE_AT: b"\x42\x78\x6e\xf0",                      # clr.w $6ef0.w
    STAGE_SPRITES_AT: b"\x43\xf9\x00\x02\x52\x98",      # lea $25298.l,a1   (WB_SPRITE_CRU_LOAD)
    STAGE_JMP_AT: b"\x4e\xf8\x04\xa0",                  # jmp $4a0.w
}

# The measured instruction counts, so each cap stays a cap. The depacker dominates every one of these
# runs and its count is a property of the STREAM rather than of a geometry a case can derive —
# test_rad_depack.py caps itself the same way and for the same reason.
PROMPT_INSN_CAP = 1_000_000         # measured 168,262
TITLE_INSN_CAP = 1_500_000          # measured 735,940
CREDITS_INSN_CAP = 1_000_000        # measured 394,190
# ...the last of them measured on the arm that also installs the sprites, over the TRUNCATED
# SPRITES.CRU the model can stage. That truncation is NOT what sets this cap's headroom: the
# installer's walk is DESCRIPTOR-driven and every descriptor lies inside the staged prefix, so a run
# over the whole file copies different CONTENT through the same instructions. What is cut short is
# the bytes each cell copier reads, never how many of them run.
STAGE_INSN_CAP = 4_000_000          # measured 2,509,776

# THE ORACLE'S WRITE LEDGER CAN TRUNCATE, AND THE KIT NOW REFUSES A DIFFERENTIAL IN WHICH IT DID.
# shim.c keeps at most MAX_WRITES write EVENTS and `logw` saturates there, while what `emu.run`
# hands back is a dict keyed by ADDRESS — so `len(info["writes"])` counts distinct BYTES and cannot
# detect the overflow at all (a guard on it was written here and measured unfirable: its threshold
# is exactly the image size). `emu.run` now reports the saturation per run and
# `harness.differential` refuses on it, so the band checks below cannot be made against a truncated
# write set without saying so.
#
# A WATCH, WITH THE GUARD BEHIND IT. These are the project's biggest runs — the stage slice's
# back-copying depacker, screen copy and two installers in one — and the measured event counts are
# 83,770 (title), 89,821 (credits) and 674,932 (the armed stage arm) against a ledger of 4,194,304,
# so the worst of them sits at 16% with 6.2x of headroom. A slice that grew past it would RED rather
# than quietly weaken every band check here.


@pytest.mark.parametrize("at", sorted(CUT_INSNS))
def test_every_cut_is_the_instruction_this_battery_believes_is_there(at):
    want = CUT_INSNS[at]
    assert bytes(harness.BASE_IMAGE[at:at + len(want)]) == want, (
        f"{at:#x} does not start with {want.hex()} — include/wonderboy.h's WB_BOOT_* cuts and the "
        f"loaded image disagree about where this slice begins or ends")


# --- two operands, read back out of the original's own instructions ----------------------------
#
# The pen is the one NOTHING else in the project can see: it goes to a shifter colour register, off
# the loaded image, and deleting the write outright is a surviving mutant (../STATUS.md §4's C3).
# The song id is not in that position — the title differential does catch a wrong one, through the
# bytes `snd_play_song` lays down for it — but it catches it as a screenful of wrong sound state
# rather than as "that is not the number the original passes". Both are therefore decoded from the
# SHIPPED IMAGE here, which is the only place either claim can be made directly.

_IMM_AT = 2                     # every one of these forms carries its immediate word at +2...
_ABS_AT = 4                     # ...and `move.w #imm,abs.l` its destination longword at +4
_BYTE_IMM_AT = 3                # `move.b #imm,abs.l` still spends a whole word on its immediate,
                                # so the BYTE the 68000 stores is the second half of it
BYTE_LEN = 1


def _operand(at, off, length):
    return int.from_bytes(bytes(harness.BASE_IMAGE[at + off:at + off + length]), "big")


def test_the_credits_pen_and_colour_are_the_ones_the_original_writes():
    """$e5a2's `move.w #$77,$ff8254.l`, decoded rather than re-typed. `CUT_INSNS` above already
    asserts the eight bytes ARE that instruction, so what is left is to read its two operands and
    require WB_CREDITS_PROMPT_PEN and WB_CREDITS_PROMPT_COLOUR to be them — the pen through the same
    WB_SHIFTER_PALETTE + index * stride arithmetic `shifter_palette_write` performs, so a pen that
    named the wrong register fails HERE, where nothing else in the project can fail on it."""
    assert _operand(CREDITS_PEN_AT, _ABS_AT, LONGWORD_LEN) \
        == SHIFTER_PALETTE + CREDITS_PROMPT_PEN * PALETTE_STRIDE, (
        f"$e5a2 writes {_operand(CREDITS_PEN_AT, _ABS_AT, LONGWORD_LEN):#x}, which is not colour "
        f"register WB_CREDITS_PROMPT_PEN ({CREDITS_PROMPT_PEN}) of WB_SHIFTER_PALETTE")
    assert _operand(CREDITS_PEN_AT, _IMM_AT, WORD_LEN) == CREDITS_PROMPT_COLOUR, (
        f"$e5a2 writes {_operand(CREDITS_PEN_AT, _IMM_AT, WORD_LEN):#x} and "
        f"WB_CREDITS_PROMPT_COLOUR is {CREDITS_PROMPT_COLOUR:#x}")


def test_the_title_song_is_the_one_the_original_asks_for():
    """$e546's `move.w #$8,d0` — the argument of the `jsr (a0)` two instructions later, and the one
    thing the title slice hands the sound module. Same discipline as the pen: the immediate is read
    out of the image, so WB_TITLE_SONG cannot drift from the number the original passes. The title
    differential catches a wrong id too (§4's T5 dies twice), but on the sound module's PRODUCT;
    this is the claim itself."""
    want = b"\x30\x3c"                                   # move.w #imm,d0
    assert bytes(harness.BASE_IMAGE[TITLE_SONG_ID_AT:TITLE_SONG_ID_AT + len(want)]) == want, (
        f"{TITLE_SONG_ID_AT:#x} is not a `move.w #imm,d0`, so WB_BOOT_TITLE_SONG_ID_AT does not "
        f"point at the instruction that names the song")
    assert _operand(TITLE_SONG_ID_AT, _IMM_AT, WORD_LEN) == TITLE_SONG, (
        f"the original asks for song {_operand(TITLE_SONG_ID_AT, _IMM_AT, WORD_LEN)} and "
        f"WB_TITLE_SONG is {TITLE_SONG}")


# `move.b #imm,abs.l`, the form both of the prompt's base writes take.
_MOVE_B_IMM_TO_ABS = b"\x13\xfc"

# (the instruction, the register it must name, how far up SCREEN_HIGH its byte comes from). The two
# halves of one address in two instructions, which is what an STF's video base register is
# (../atari/wonderboy_backend.c): bits 23-16 and 15-8, and no low byte at all.
PROMPT_BASE_WRITES = (
    (PROMPT_BASE_HI_AT, wb("SHIFTER_SCREEN_BASE_HIGH"), 16),
    (PROMPT_BASE_MID_AT, wb("SHIFTER_SCREEN_BASE_MID"), 8),
)


@pytest.mark.parametrize("at,register,shift", PROMPT_BASE_WRITES,
                         ids=["$ff8201 (bits 23-16)", "$ff8203 (bits 15-8)"])
def test_the_prompt_points_the_shifter_at_the_buffer_its_picture_lands_in(at, register, shift):
    """$e498 and $e4a0, decoded rather than re-typed — the ONE claim in this slice that no memory
    differential can make. Both writes go to the shifter, off the loaded image, so the oracle drops
    them and src/boot.c's sink compiles to nothing off target; the credits pen's cell (§4's C3) one
    slice over is the same hole. WHAT IS STATED HERE is the write's IDENTITY: that the register is
    the one WB_SHIFTER_SCREEN_BASE_* names, and that the byte is the corresponding half of
    WB_SCREEN_HIGH — which is WB_PROMPT_SCREEN_BASE, and which the picture case below independently
    shows is the buffer WB_PROMPT_DEPACK_DEST inflates into. Together those two say the base and the
    depack are one arrangement, which is the thing a derived #define cannot say for itself."""
    assert bytes(harness.BASE_IMAGE[at:at + len(_MOVE_B_IMM_TO_ABS)]) == _MOVE_B_IMM_TO_ABS, (
        f"{at:#x} is not a `move.b #imm,abs.l`, so WB_BOOT_PROMPT_BASE_* does not point at one of "
        f"the two instructions that publish the screen base")
    assert _operand(at, _ABS_AT, LONGWORD_LEN) == register, (
        f"{at:#x} writes {_operand(at, _ABS_AT, LONGWORD_LEN):#x}, not the shifter register "
        f"{register:#x} the port's screen-base sink sends this byte to")
    assert _operand(at, _BYTE_IMM_AT, BYTE_LEN) == (SCREEN_HIGH >> shift) & 0xff, (
        f"{at:#x} publishes {_operand(at, _BYTE_IMM_AT, BYTE_LEN):#x} where bits {shift + 7}-{shift} "
        f"of WB_SCREEN_HIGH ({SCREEN_HIGH:#x}) are {(SCREEN_HIGH >> shift) & 0xff:#x} — the prompt "
        f"would show a buffer its own depack does not fill")


def test_the_stage_slice_starts_where_the_name_map_puts_the_dispatcher():
    """WB_BOOT_STAGE_AT has no `var` of its own and cannot have one: ../../names.txt already gives
    $e5ba to `stage_sequence_advance`, which is this slice's FIRST piece and had the address first
    (one address carries one name). So the cross-pin is against that name, and the two other slices
    are pinned by their instruction bytes above — they lie inside show_data_disk_prompt's Ghidra body
    and carry `cmt` plates rather than directives."""
    assert STAGE_AT == leaf.entry_of("stage_sequence_advance"), (
        f"WB_BOOT_STAGE_AT is {STAGE_AT:#x} and the name map puts stage_sequence_advance at "
        f"{leaf.entry_of('stage_sequence_advance'):#x}")


# --- the picture geometry the two depack destinations rest on -------------------------------------

PICTURES = (("TITLESCR.RAD", "disk1", TITLE_DEPACK_DEST, SCREEN_LOW),
            ("CREDITS.RAD", "disk1", CREDITS_DEPACK_DEST, SCREEN_HIGH),
            # ...and the third picture, which `boot_prompt_screen` draws through the same three
            # calls into the same buffer. Its row is what says WB_PROMPT_DEPACK_DEST — a derived
            # #define spelt as the credits one — is right for THIS file and not only for CREDITS.RAD.
            ("DATADISK.RAD", DISK2, CREDITS_DEPACK_DEST, SCREEN_HIGH))


@pytest.mark.parametrize("name,where,dest,screen", PICTURES, ids=[p[0] for p in PICTURES])
def test_a_picture_inflates_to_a_prefix_and_exactly_one_screen(name, where, dest, screen):
    """WHY THE DEPACK IS AIMED BELOW A SCREEN BUFFER, from the files' own headers rather than from
    the comment beside the operand: each picture unpacks to WB_RAD_PICTURE_PREFIX + WB_SCREEN_BYTES,
    so a depack aimed WB_RAD_PICTURE_PREFIX below a buffer lands the picture IN it and leaves the
    palette row the next call reads inside the prefix. Every `lea` operand src/boot.c carries is one
    of these three numbers."""
    data = (BIN / where / name).read_bytes()
    unpacked = depack_rad.parse_header(data).unpacked_size
    assert unpacked == PICTURE_PREFIX + SCREEN_BYTES, (
        f"{name} inflates to {unpacked} bytes, not the {PICTURE_PREFIX}-byte prefix plus one "
        f"{SCREEN_BYTES}-byte screen the depack destinations are chosen for")
    assert dest + PICTURE_PREFIX == screen, (
        f"{dest:#x} + {PICTURE_PREFIX} is not {screen:#x}, so this picture does not land in the "
        f"screen buffer the slice then shows")
    assert PICTURE_PALETTE_OFF < PICTURE_PREFIX, (
        f"the palette row sits {PICTURE_PALETTE_OFF} bytes into a {PICTURE_PREFIX}-byte prefix — "
        f"at or past it, `set_palette` would be reading the picture's own bitplanes")


# --- driving a slice ------------------------------------------------------------------------------

def _park_saved_sp(buf):
    """Give the candidate the stack pointer the original's `jsr rad_depack` will have pushed.

    NOT an assumption this case makes true. All four of the boot's depack calls are a plain `jsr`
    from their slice's own top level, so the oracle has pushed exactly one return address by the time
    `move.l a7,WB_RAD_SAVED_SP` runs — and if that were wrong, the ORACLE's write would be a
    different longword and the diff would say so. The candidate side is written here rather than as a
    `g_boot_*` glue in src/boot.c because the value is a fact about the RUNNER's stack, which only a
    case knows.
    """
    for index, byte in enumerate((emu.STACK_TOP - LONGWORD_LEN).to_bytes(RAD_SAVED_SP_LEN, "big")):
        buf[RAD_SAVED_SP + index] = byte


def _slice_glue(name, park=True):
    """Candidate glue for one composed slice: park the SP above, then run it.

    ``park`` is off for the candidate-only case that ENUMERATES every byte that changed: there is no
    oracle write to match there, and four bytes of the harness's own would read as the slice's. The
    other candidate-only cases leave it on, which is harmless — WB_RAD_SAVED_SP lies outside every
    region they inspect — and keeps them running the glue the differentials run.
    """
    slice_fn = leaf.bind(name, leaf.IMAGE_ARG, ctypes.c_uint32)

    def run(_lib, buf):
        if park:
            _park_saved_sp(buf)
        return slice_fn(buf)
    return run


def _boot_owned_bands(pokes):
    """The BOUND two of these cases put on the oracle's writes, and it is a bound and not a model.

    "Nothing above the two screen buffers, except the staged-file table entries the seam updates."
    That is a real property — it says the slice scribbles into neither the model's staging area nor
    the band above the screens — and it is ALL those cases claim about the write SET, for the reason
    the module docstring gives. Said plainly, because the name flatters it: the permitted band is
    [0, WB_SCREEN_HIGH + WB_SCREEN_BYTES), which is the whole program, all of its data and every
    buffer the game owns, so this constrains NOTHING about where inside the game's own memory a
    slice wrote. The byte-for-byte image diff is what pins that; this only watches the oracle.
    `leaf.stray_writes` permits the machine stack on top of it.

    The table band is DERIVED from the run's own poke dict rather than counted at the call site: a
    case that stages one more file would otherwise loosen this bound silently.
    """
    table = harness.OS_FS_TABLE
    entries = sum(1 for at in pokes if table <= at < table + harness.OS_FS_ENTRY * harness.OS_FS_SLOTS)
    return [(0, SCREEN_HIGH + SCREEN_BYTES), (table, harness.OS_FS_ENTRY * entries)]


def _run_slice(entry, name, stop_pc, transfer, pokes, allowed, what, max_insns, witnesses=()):
    """One slice's differential: the whole image, the oracle's write set, and the witness that the
    run really reached its end instead of returning early.

    ``allowed`` is the write set the ORACLE may touch — stated exactly by the title case and bounded
    by `_boot_owned_bands` by the other two, for the reason the module docstring gives.

    THE ATTRIBUTION PASS IS OFF on every case here, which `leaf.run`'s docstring makes a deviation a
    caller must justify. Poisoning inverts the bytes the oracle wrote and re-runs both cores over
    them — and the bytes these slices write include WB_RESOURCE_LOAD_BUFFER, which is the DEPACKER'S
    OWN INPUT, and the resource table the second half of the run reads back. Inverting them does not
    re-run this function; it runs a different one. test_stage.py's hinge cases turn it off for the
    same reason, one tier down.

    THE WITNESS IS OWED. A `stop_pc` run stops at EITHER the checkpoint or an `rts`, and the kit
    reports only that one of them fired (leaf.run's own docstring). Each slice's last instruction is
    `transfer`, so requiring the oracle to have executed it is the positive evidence that the run
    walked the whole slice — `leaf.run_reaching`'s discipline, spelt here because these entries have
    no `fn` of their own to hand `leaf.run`.

    ``witnesses`` is (address, was-it-executed) for any OTHER instruction the case is about: an arm
    is claimed both ways, so a case that means "this run did not take the second load" says so and
    is not left resting on the byte diff.

    THE PSG SEED IS HANDED TO EVERY SLICE, and which slices need it was MEASURED rather than
    reasoned about. The title slice reads the mixer through `snd_play_song` — and so does the STAGE
    slice, through the hinge: `stage_load_window` ends in the stage's own tune, which is `snd_stop`
    or `snd_play_song` depending on the START record the row names, and both reach the chip. Making
    the declaration per-slice would therefore make it per-ROW, and a case that refuses or is served
    according to which sequence row it drives is a worse thing than one inert declaration.
    """
    with leaf.pc_coverage():
        diffs, info = harness.differential(entry, {"_pokes": pokes}, _slice_glue(name),
                                           stop_pc=stop_pc, max_insns=max_insns, poison=False,
                                           psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
        assert not diffs, f"{what}\n{harness.report(diffs)}"
        reached = emu.cov_visited(transfer)
        seen = {at: emu.cov_visited(at) for at, _ in witnesses}
    assert reached, (
        f"{what}: the run stopped at {stop_pc:#x} without executing {transfer:#x}, so it RETURNED "
        f"early rather than walking the slice to its end")
    for at, want in witnesses:
        assert seen[at] == want, (
            f"{what}: the original {'did not reach' if want else 'reached'} {at:#x}, so this case "
            f"is not about the arm it says it is")
    stray = leaf.stray_writes(info["writes"], allowed)
    assert not stray, (
        f"{what}: {len(stray)} write(s) outside {[(hex(a), n) for a, n in allowed]}, e.g. "
        f"{harness.label(stray[0])} @ {stray[0]:#x}")
    return info


# --- the prompt slice ($e494..$e4d4) --------------------------------------------------------------
#
# THE ONE SLICE THE BOOT DOES NOT RUN. `show_data_disk_prompt` is entered by a `jmp $e494.l`, and
# the shipped image holds THREE of them — $598 (ESC's `game_key_actions` arm, the only one that
# fades the music first), $bdc (the player gate's game-over box expiring) and $700e (slot 61's
# message terminator, which the Copylock failure path also reaches). ../src/boot.c has the census.
# Its own fire wait falls through into $e4e6, so the slice is each of those restarts' first half and
# the boot continuation is its second. Same shape as the title slice and a shorter one: a clear, a
# base publish, a load, a depack and a palette, with nothing armed and no sound.
#
# THE CUTS BELOW ARE THE SLICE'S ($e494..$e4d4) AND NOT THE ROUTINE'S PROMPT HALF ($e494..$e4e4):
# $e4d6..$e4e4 is the fire wait, which is hardware and is the shim's.

DATADISK = BIN / DISK2 / "DATADISK.RAD"


def _prompt_pokes():
    """Just the staged file. NOTHING ELSE NEEDS SEEDING and that is a property of the slice rather
    than an omission: its two hardware calls (`clear_palette`, the base publish) write no image byte
    at all, and the other three write the load buffer, the picture and `load_resource_by_index`'s two
    retry longwords — none of which the shipped image already holds the post-run value of. The
    credits slice needs `_reset_pokes` because fifteen of `game_restart_reset`'s stores land on bytes
    that already hold what it writes; this slice has no such store."""
    return seam_pokes([("DATADISK.RAD", DATADISK.read_bytes())])


def _prompt_allowed():
    """The prompt slice's write set, stated EXACTLY — the title slice's discipline, and it is shorter
    here because two of this slice's five calls touch no image byte. So a composition that also
    cleared a screen, or copied one down onto the other buffer as the credits slice does, fails on
    the band it had no business touching as well as on the bytes."""
    return [(CREDITS_DEPACK_DEST, PICTURE_PREFIX + SCREEN_BYTES),      # $e4c6's depack
            (RESOURCE_LOAD_BUFFER, DATADISK.stat().st_size),          # ...and where it read it from
            (RAD_SAVED_SP, RAD_SAVED_SP_LEN),                         # the depacker's parked a7
            (LOAD_RETRY_INDEX, LONGWORD_LEN), (LOAD_RETRY_DEST, LONGWORD_LEN),
            (FLOPPY_IDLE_TIMER, WORD_LEN),                            # the seam's re-armed fuse
            (harness.OS_FS_TABLE, harness.OS_FS_ENTRY)]


def test_the_prompt_slice_draws_the_data_disk_screen():
    """$e494..$e4d4 whole, over the shipped DATADISK.RAD, with the write set stated exactly.

    IT ARMS NOTHING, which is the row below: WB_COPYLOCK_ARM_FLAG is never written on this path, so
    the slice reports WB_LOAD_OK and the protection is not claimed to have run. That distinguishes it
    from the title slice, whose otherwise identical three calls are preceded by `$e51e`."""
    pokes = _prompt_pokes()
    info = _run_slice(PROMPT_AT, "boot_prompt_screen", PROMPT_END, PROMPT_PALETTE_AT,
                      pokes, _prompt_allowed(),
                      "boot_prompt_screen over DATADISK.RAD", PROMPT_INSN_CAP)
    assert info["ret"] == LOAD_OK, (
        f"the slice reported {info['ret']}, not WB_LOAD_OK — nothing on this path arms the "
        f"protection, so no load of it can take load_resource_by_index's armed arm")


def test_the_prompt_slice_leaves_the_other_buffer_alone():
    """WHY THIS SLICE NEEDS NO `copy_screen`, as a property rather than as a band in the list above.

    `boot_credits_screen` inflates into WB_SCREEN_HIGH and then copies the picture DOWN onto
    WB_SCREEN_LOW, because the prologue pointed the shifter at the low buffer. This slice points the
    shifter at the HIGH one first ($e498/$e4a0, the two operand cases above) and so shows the buffer
    it inflates into — which is only true while WB_SCREEN_LOW comes out untouched. Candidate-only,
    and sound because the differential above carries the same region to the original byte for byte;
    what this adds is the claim said in its own terms, so a port that grew a copy fails on a row
    that names the reason instead of only on 32000 bytes of diff."""
    poison = bytes([POISON]) * LONGWORD_LEN
    pokes = {**_prompt_pokes(), SCREEN_LOW: poison}
    ret, image = leaf.run_candidate_only(_slice_glue("boot_prompt_screen"), pokes)
    assert ret == LOAD_OK, f"the slice stopped early ({ret}), so it never drew anything"
    assert bytes(image[SCREEN_LOW:SCREEN_LOW + len(poison)]) == poison, (
        "the prompt slice wrote WB_SCREEN_LOW — it copied its picture down onto the buffer the "
        "credits slice copies onto, and the shifter is not pointed there")
    assert bytes(image[SCREEN_HIGH:SCREEN_HIGH + SCREEN_BYTES]) != bytes(SCREEN_BYTES), (
        "WB_SCREEN_HIGH came out all zeros, so this slice drew no picture at all and the assertion "
        "above is about an empty buffer")


# --- the title slice ($e512..$e550) ---------------------------------------------------------------

TITLESCR = BIN / "disk1" / "TITLESCR.RAD"


def _title_pokes():
    pokes = seam_pokes([("TITLESCR.RAD", TITLESCR.read_bytes())])
    # The sound module's two mutable bands, seeded so a store `snd_play_song` skipped leaves a byte
    # that is wrong FOR ITS ADDRESS rather than the .PRG's residue — test_sound.py's own rule for
    # every case that reaches this routine.
    salt = leaf.case_salt("boot_title_screen")
    pokes.update({base: leaf.keyed_block(base, length, salt)
                  for base, length in PLAY_SONG_SEEDED_BANDS})
    return pokes


def _title_allowed(image):
    """The title slice's write set, stated EXACTLY: its three callees are the depacker, the palette
    (which writes no image byte at all) and the sound module, and the last of those has a model in
    test_sound.py this case reuses rather than restates."""
    return leaf.merge_bands(leaf.seeded_bytes(model_play_song(image, TITLE_SONG))) + [
        (TITLE_DEPACK_DEST, PICTURE_PREFIX + SCREEN_BYTES),      # $e536's depack
        (RESOURCE_LOAD_BUFFER, TITLESCR.stat().st_size),         # ...and where it read it from
        (RAD_SAVED_SP, RAD_SAVED_SP_LEN),                        # the depacker's parked a7
        (LOAD_RETRY_INDEX, LONGWORD_LEN), (LOAD_RETRY_DEST, LONGWORD_LEN),
        (COPYLOCK_ARM_FLAG, COPYLOCK_ARM_FLAG_LEN),
        (FLOPPY_IDLE_TIMER, WORD_LEN),                           # the seam's re-armed fuse
        (harness.OS_FS_TABLE, harness.OS_FS_ENTRY),
    ]


def test_the_title_slice_draws_the_title_screen_and_starts_its_tune():
    """$e512..$e550 whole, over the shipped TITLESCR.RAD, with the write set stated exactly — so a
    composition that also cleared a screen, or copied one, or depacked to the wrong buffer, fails on
    the band it had no business touching as well as on the bytes."""
    pokes = _title_pokes()
    info = _run_slice(TITLE_AT, "boot_title_screen", TITLE_END, TITLE_SONG_AT,
                      {**pokes, **copylock.stub_pokes(copylock.Stub.ENTRY_RTS)},
                      _title_allowed(harness.make_image(pokes)),
                      "boot_title_screen over TITLESCR.RAD", TITLE_INSN_CAP)
    assert info["ret"] == LOAD_COPYLOCK_RAN, (
        f"the slice reported {info['ret']}, not WB_LOAD_COPYLOCK_RAN — $e51e's `move.w #$ffff,"
        f"$e7cc.l` did not reach the load, so the protection would not have run where it does")


def test_the_title_slice_runs_the_protection_and_leaves_it_disarmed():
    """THE WITNESS THE DIFFERENTIAL ABOVE CANNOT CARRY. `harness.differential` does not hand back the
    image the Copylock witness compares against (copylock.py's docstring names this class of case as
    the one that must ask by hand), so the same run is driven once more through `copylock.run`, which
    asserts the blob did not execute before it returns anything. Without it, "the two sides agree"
    would be a statement about whatever a trace decryptor left behind."""
    after, _, _ = copylock.run(TITLE_AT, copylock.Stub.ENTRY_RTS, _title_pokes(),
                               stop_pc=TITLE_END, max_insns=TITLE_INSN_CAP,
                               psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    assert bytes(after[COPYLOCK_ARM_FLAG:COPYLOCK_ARM_FLAG + COPYLOCK_ARM_FLAG_LEN]) \
        == copylock.DISARMED, (
        "the slice left copylock_arm_flag armed, so the next load would run the guard again")
    assert bytes(after[SCREEN_LOW:SCREEN_LOW + SCREEN_BYTES]) != bytes(SCREEN_BYTES), (
        f"the original left WB_SCREEN_LOW all zeros, so this slice drew no picture at all and the "
        f"differential above is comparing two empty buffers")


# --- the credits slice ($e562..$e5a2) -------------------------------------------------------------

CREDITS = BIN / "disk1" / "CREDITS.RAD"
CREDITS_ROW = "CREDITS .RAD"      # the FAT12-padded name the game's own table holds (test_boot.py)


# WB_LIVES the credits case seeds. NOT WB_LIVES_ON_RESTART: `game_restart_reset` writes that value
# whatever it finds, so a case that started there could not tell the store from a no-op.
CREDITS_LIVES_SEED = LIVES_ON_RESTART + 1


def _credits_pokes():
    """The staged file, plus every band `game_restart_reset` writes, seeded.

    WITHOUT THIS THE RESET IS TRUE FOR THE WRONG REASON, and it was measured: FIFTEEN of the twenty
    or so addresses it stores to already hold in the shipped `.PRG` exactly the value it writes —
    WB_LIVES is 3 and it writes 3, the effect list is $ffff and it writes $ffff, and a dozen state
    words are zero and are written zero. A composed differential run on the shipped bytes would
    therefore stay green with any of those fifteen stores deleted. `test_stage.py`'s own reset
    battery already states which bands they are, so its seeding is imported rather than restated.

    The attribution PASS (`poison=True`) is not available here for the reason `_run_slice` gives, so
    seeding is what stands in for it — the same substitution `_title_pokes` makes for the sound
    module's mutable bands.
    """
    salt = leaf.case_salt("boot_credits_screen")
    return {**seam_pokes([(CREDITS_ROW, CREDITS.read_bytes())]),
            **_reset_pokes(salt, CREDITS_LIVES_SEED)}


def test_the_credits_slice_draws_the_credits_and_resets_the_game():
    """$e562..$e5a2 whole: the load, the depack onto WB_SCREEN_HIGH, the palette, the copy down onto
    the buffer the shifter is showing, and the new-game reset — every byte of both screen buffers and
    of the twelve state bands the reset clears.

    IT DOES NOT SEE THE ORDER OF ITS LAST TWO STEPS, and that was measured rather than assumed:
    swapping them is a SURVIVING mutant. `game_restart_reset` draws the lives into BOTH screen
    buffers at the same offsets, and the copy makes the two equal either way, so reset-then-copy and
    copy-then-reset end on identical memory. The order is faithful to the listing and it is not
    pinned here; nothing off target can pin it."""
    pokes = _credits_pokes()
    info = _run_slice(CREDITS_AT, "boot_credits_screen", CREDITS_END, CREDITS_PEN_AT,
                      pokes, _boot_owned_bands(pokes),
                      "boot_credits_screen over CREDITS.RAD", CREDITS_INSN_CAP)
    assert info["ret"] == LOAD_OK, (
        f"the slice reported {info['ret']}, not WB_LOAD_OK — nothing arms the protection here")


# --- the stage slice ($e5ba..$f8b4) ---------------------------------------------------------------
#
# THE SEQUENCE ROW IS THE PARAMETER. It names the overlay to load, whether the stage's sprites are
# loaded with it, which side the stage is entered from and which stage number the sprite mask is
# taken from — so the cases below are rows, and the rows are the game's own.

TILEDATA = BIN / DISK2 / "TILEDATA.RAD"
SPRITES_CRU = BIN / DISK2 / "SPRITES.CRU"
RESOURCE_FILE_TABLE = wb("RESOURCE_FILE_TABLE")
RESOURCE_FILE_ROW_SHIFT = wb("RESOURCE_FILE_ROW_SHIFT")
RESOURCE_FIRST_OVERLAY = wb("RESOURCE_FIRST_OVERLAY")
SPRITES_CRU_ROW = "SPRITES .CRU"
RESOURCE_FILE_ROW_BYTES = 1 << RESOURCE_FILE_ROW_SHIFT


def _row_name(index):
    """The filename WB_RESOURCE_FILE_TABLE's row `index` holds — the same twelve bytes the seam is
    handed, read out of the image rather than typed here."""
    at = RESOURCE_FILE_TABLE + index * RESOURCE_FILE_ROW_BYTES
    raw = bytes(harness.BASE_IMAGE[at:at + RESOURCE_FILE_ROW_BYTES])
    return raw[:raw.index(b"\x00")].decode("ascii")


@functools.lru_cache(maxsize=None)
def _overlay_of(row):
    """(staged name, bytes) for the overlay sequence row `row` names."""
    ordinal = harness.BASE_IMAGE[_row_of(row) + wb("LEVEL_SEQ_OVERLAY")]
    name = _row_name((ordinal + RESOURCE_FIRST_OVERLAY) & 0xff)
    return name, (BIN / DISK2 / name.replace(" ", "")).read_bytes()


# How many of the shipped rows take the ONE-LOAD arm on a first entry. Recorded so the count in
# src/boot.c's banner is a measurement rather than a recollection.
SHIPPED_ONE_LOAD_ROWS = 24


def _second_load_byte(row):
    return harness.BASE_IMAGE[_row_of(row) + LEVEL_SEQ_SECOND_LOAD]


def _stage_pokes(row, reentry, sprites):
    """The run's staged files, its sequence index and its re-entry word — and the three actor tables,
    seeded for `_credits_pokes`' reason: `stage_actors_init` marks nineteen records free in each, and
    the shipped bytes are already zero there, so an unseeded run cannot tell those stores from
    no-ops. test_boot.py's own `stage_actors_init` cases poison the same three bands."""
    name, overlay = _overlay_of(row)
    files = [(name, overlay), ("TILEDATA.RAD", TILEDATA.read_bytes())]
    if sprites:
        files.append((SPRITES_CRU_ROW, _sprites_prefix(len(overlay))))
    salt = leaf.case_salt(f"boot_load_stage row {row} reentry {reentry} sprites {sprites}")
    return {**seam_pokes(files),
            **{table: leaf.keyed_block(table, ACTOR_TABLE_SPAN, salt) for table in ACTOR_TABLES},
            LEVEL_SEQ_INDEX: row.to_bytes(WORD_LEN, "big"),
            LIFE_RESTART_ENTRY_C26: reentry.to_bytes(WORD_LEN, "big")}


def _sprites_prefix(overlay_bytes):
    """As much of the shipped SPRITES.CRU as the model can hold beside the other two staged files.

    DERIVED, not chosen: the boundary is the staging area, so it is computed from the area and from
    what else this run stages. Everything before the truncation is the game's own file, descriptor
    table included, so every copier selector and cell count the walk reads is real; what a sprite
    past the cut copies is whatever the image holds there, identically on both sides.
    """
    room = STAGING_CAPACITY - overlay_bytes - TILEDATA.stat().st_size
    return SPRITES_CRU.read_bytes()[:room]


# What `sprites_cru_install`'s walk READS before it copies anything: the slide moves this many
# LONGWORDS down from the file's own first byte, and everything the walk decides with — the .CRU
# header, WB_RESOURCE_TABLE's records, every descriptor's copier selector and cell count — is inside
# them. A staged prefix shorter than this would be a walk over invented descriptors.
SPRITES_CRU_DESCRIPTOR_BYTES = wb("SPRITE_CRU_SLIDE_LONGS") * LONGWORD_LEN


def test_the_sprites_file_is_staged_as_the_prefix_the_model_can_hold():
    """The armed arm's one deviation, MEASURED and bounded rather than described. test_boot.py
    already says SPRITES.CRU is the one boot resource the model cannot stage; this says how much of
    it the arm's case does stage, that what is staged is a genuine prefix of the shipped file, and
    that the prefix covers the whole DESCRIPTOR region the installer's walk reads.

    WHAT ESCAPES, named rather than left implied: a descriptor whose CELL WORDS lie past the cut
    copies whatever the image holds there instead of the file's bytes, and the shipped mask marks
    many such. It is the same residue on both sides, so the CHAIN this file pins is unaffected — and
    the installer's PRODUCT over the whole file is test_boot.py's per-stage
    differentials, which poke the entire file into the image and never go through the seam."""
    overlay = len(_overlay_of(0)[1])
    prefix = _sprites_prefix(overlay)
    whole = SPRITES_CRU.read_bytes()
    assert len(whole) > STAGING_CAPACITY, (
        f"SPRITES.CRU is {len(whole)} bytes and the staging area is {STAGING_CAPACITY} — it FITS, "
        f"so the armed arm should be driven over the whole file and this deviation deleted")
    assert whole.startswith(prefix), (
        f"the staged {len(prefix)} bytes are not a prefix of the shipped {len(whole)}")
    assert len(prefix) >= SPRITES_CRU_DESCRIPTOR_BYTES, (
        f"the staged prefix is {len(prefix)} bytes and the installer reads its descriptors out of "
        f"the first {SPRITES_CRU_DESCRIPTOR_BYTES} — the walk would be steered by bytes no file "
        f"put there, and both cores would agree about a run that means nothing")
    assert overlay + TILEDATA.stat().st_size + len(prefix) == STAGING_CAPACITY, (
        "the three staged files do not fill the staging area, so the prefix is shorter than it "
        "needs to be and the arm reads more fabricated bytes than it has to")


# THE a5 THE BOOT LEAVES FOR THE FRAME LOOP, and where it comes from.
#
# `sprite_draw_pass` has one register that is a real input — `blit.unwind`, a5 (../include/blit.h) —
# and ../atari/'s frame builds seed it from `build/ORIGREGS.txt`, the ORIGINAL's measured A5 at
# `$f8b4`. An OWN-ENTRY build has no dump to take it from, so it has to know who PRODUCES it, and
# these two rows are that answer measured rather than argued.
#
# THE PRODUCER IS `bg_build_buffer`'s `lea $21e90.l,a5` at $fa5e — the one instruction in the hinge
# that writes a5, run once per map cell on the arm the shipped tile bank takes. Its operand is
# WB_TILE_INDEX_TABLE, which is the table ../src/stage.c's `tile_number` already reads through, so
# the own-entry build's `M2_ENTRY_UNWIND` is not a new constant and not a copied measurement.
#
# WHAT THE ORACLE IS ASKED. Every `_run_stage` case below runs the SHIPPED code from $e5ba to the
# `jmp $4a0.w`, so `info["a5"]` is the 68000's own a5 at the instant the frame loop is entered — on
# a run staged from the program image alone. Measured: $21e90 on all three arms, and $1d43e in a6,
# which is WB_TILE_BITMAPS and therefore the reason the indexed arm was the one taken.
BOOT_ENTRY_UNWIND = wb("TILE_INDEX_TABLE")
TILE_BITMAPS = wb("TILE_BITMAPS")


def _assert_the_boot_produces_the_frame_loops_unwind(info, what):
    """a5 and a6 at the `jmp $4a0.w`, out of the oracle's own register file.

    NOT A CLAIM ABOUT THE PORT — nothing in ../src/ keeps a5, and the C composition has no such
    register — but about what the ORIGINAL leaves there, which is the fact ../atari/'s own-entry
    build needs and would otherwise have to take from a dump. The a6 row is what makes the a5 row
    mean something: `stage_load_window`'s `cmpa.l #$1d43e,a6` is what clears WB_STAGE_RAW_TILE_INDEX
    and so what makes `$fa5e` execute at all, and a run handed a different bank would leave a5 at
    whatever it happened to hold."""
    regs = info["regs"]      # emu.REPORTED_REGS — the ORACLE's d0..d7/a0..a6 at the stop
    assert regs["a6"] == TILE_BITMAPS, (
        f"{what}: the hinge was handed a tile bank of {regs['a6']:#x} and not WB_TILE_BITMAPS "
        f"({TILE_BITMAPS:#x}), so `bg_build_buffer`'s indexed arm need not have run and the a5 "
        f"below would be whatever the boot left rather than what it produced")
    assert regs["a5"] == BOOT_ENTRY_UNWIND, (
        f"{what}: the original entered game_main_loop with a5 = {regs['a5']:#x}, and $fa5e's "
        f"`lea $21e90.l,a5` makes it WB_TILE_INDEX_TABLE ({BOOT_ENTRY_UNWIND:#x}) — the number "
        f"../atari/wonderboy_main.c compiles into the own-entry build as M2_ENTRY_UNWIND")


def _run_stage(row, reentry, sprites, what):
    pokes = _stage_pokes(row, reentry, sprites)
    info = _run_slice(STAGE_AT, "boot_load_stage", STAGE_END, STAGE_JMP_AT,
                      {**pokes, **copylock.stub_pokes(copylock.Stub.ENTRY_RTS)},
                      _boot_owned_bands(pokes), what, STAGE_INSN_CAP,
                      witnesses=((STAGE_SPRITES_AT, sprites),))
    assert info["ret"] == (LOAD_COPYLOCK_RAN if sprites else LOAD_OK), (
        f"{what}: the slice reported {info['ret']}, which is not what the "
        f"{'armed' if sprites else 'one-load'} arm gives")
    _assert_the_boot_produces_the_frame_loops_unwind(info, what)
    return info


def test_the_stage_slice_loads_a_stage_it_is_re_entering():
    """WB_LIFE_RESTART_ENTRY_C26 nonzero: a life lost. `stage_sequence_advance` leaves
    WB_STAGE_SECOND_LOAD_FLAG at zero however the row is filled, so the stage is rebuilt WITHOUT
    reloading SPRITES.CRU — and without running the protection a second time. Row 0 is the boot's own
    first stage, whose row DOES ask for the second load, so the arm here is the re-entry's doing."""
    assert _second_load_byte(0) != 0, (
        "sequence row 0 does not ask for a second load, so this case's re-entry suppresses nothing")
    _run_stage(0, reentry=1, sprites=False, what="boot_load_stage re-entering row 0")


def test_a_shipped_row_that_asks_for_no_second_load_takes_the_same_arm_on_a_first_entry():
    """The complement, driven by the GAME'S OWN DATA rather than by a re-entry: most of the 35
    sequence rows carry a zero in their second-load byte, so a first entry to one of them skips the
    sprites too. Without this the one-load arm would be reachable only through a poked re-entry.

    THE COUNT IS MEASURED, not written down: src/boot.c's banner first claimed three, and the table
    holds twenty-four. A number in prose that nothing counts is a number that drifts."""
    rows = [n for n in range(wb("LEVEL_SEQ_ROWS")) if _second_load_byte(n) == 0]
    assert len(rows) == SHIPPED_ONE_LOAD_ROWS, (
        f"{len(rows)} of the shipped sequence rows ask for no second load, not the recorded "
        f"{SHIPPED_ONE_LOAD_ROWS}")
    row = rows[0]
    _run_stage(row, reentry=0, sprites=False, what=f"boot_load_stage over shipped row {row}")


def test_the_stage_slice_loads_the_stages_sprites_on_a_first_entry():
    """THE ARMED ARM, and the whole chain with it: the sequence row, the overlay, the resource
    table's park and restore, TILEDATA.RAD, the tile installer, SPRITES.CRU, the sprite installer,
    the actors, the relocation, the reset and the hinge. The file is the prefix the model can hold
    (see above) — what this pins is the CHAIN, and test_boot.py pins the installer's product over the
    whole file."""
    _run_stage(0, reentry=0, sprites=True, what="boot_load_stage over row 0, first entry")


def test_the_armed_arm_runs_the_protection_and_leaves_it_disarmed():
    """The Copylock witness for the arm that ARMS it, asked by hand for the title slice's reason.

    ITS ASSERTION IS ABOUT THE ORIGINAL, not about the port — `copylock.run` drives the oracle alone
    — and that is what it is for: it says the run the differential above compared against was the
    game's own memory and not a trace decryptor's leavings.

    IT DOES NOT ALSO CLAIM `$e6ec`'s `clr.w $c26.w`, and an earlier revision did. The armed arm is
    only reachable while WB_LIFE_RESTART_ENTRY_C26 is ALREADY zero — that word is what
    `stage_sequence_advance` gates the second load on — so a case on this arm cannot tell the clear
    from a no-op. The RE-ENTRY differential is where that store is observable, and it is what kills
    a port that drops it."""
    pokes = _stage_pokes(0, reentry=0, sprites=True)
    after, _, _ = copylock.run(STAGE_AT, copylock.Stub.ENTRY_RTS, pokes, stop_pc=STAGE_END,
                               max_insns=STAGE_INSN_CAP,
                               psg_seed={PSG_REG_MIXER: PLAY_SONG_MIXER})
    assert bytes(after[COPYLOCK_ARM_FLAG:COPYLOCK_ARM_FLAG + COPYLOCK_ARM_FLAG_LEN]) \
        == copylock.DISARMED, "the arm left copylock_arm_flag armed, so it would run again"


def test_the_resource_table_survives_the_overlay_that_inflates_over_it():
    """WHAT THE PARK AND RESTORE ARE FOR, as a property rather than as bytes in a diff.

    The overlay inflates from WB_OVERLAY_DEPACK_DEST and CROSSES WB_RESOURCE_HEADER — asserted here
    out of the file's own header, so a smaller overlay would fail this case instead of making it
    vacuous — and the table comes out the other side untouched. Driven on the candidate alone, which
    is sound only because the differentials above carry it to the original: they compare this same
    region byte for byte on all three arms.
    """
    header = wb("RESOURCE_HEADER")
    span = wb("RESOURCE_TABLE_SAVE_LONGS") * LONGWORD_LEN
    name, overlay = _overlay_of(0)
    reach = wb("OVERLAY_DEPACK_DEST") + depack_rad.parse_header(overlay).unpacked_size
    assert reach > header, (
        f"{name} inflates only to {reach:#x}, which does not reach WB_RESOURCE_HEADER at "
        f"{header:#x} — nothing would be at risk and this case would prove nothing")

    # MARKED, AND MARKED AS ALREADY RELOCATED. `resource_table_relocate` runs later in this same
    # slice and rewrites the table IN PLACE — so a block that came back changed would be ambiguous
    # between "the park failed" and "the relocation ran". Its guard is the signature byte at
    # WB_RESOURCE_HEADER, so a block that opens with WB_RESOURCE_RELOCATED is left alone and the
    # window this case observes is the whole slice rather than a prefix of it.
    marked = (bytes([wb("RESOURCE_RELOCATED")])
              + leaf.keyed_block(header, span, leaf.case_salt("resource table"))[1:])
    # A RE-ENTRY, so every load the run makes is one this case stages and the slice runs to its end
    # rather than stopping at a SPRITES.CRU nothing put in the model.
    pokes = {**_stage_pokes(0, reentry=1, sprites=False), header: marked}
    ret, image = leaf.run_candidate_only(_slice_glue("boot_load_stage"), pokes)
    assert ret == LOAD_OK, f"the slice stopped early ({ret}), so it never reached the restore"
    assert bytes(image[header:header + span]) == marked, (
        f"the {span} parked bytes did not come back: the first byte to differ is at "
        f"{header + next(i for i in range(span) if image[header + i] != marked[i]):#x}")


# --- the stop: a load the seam refuses ------------------------------------------------------------
#
# WHAT EACH SLICE HAS ALREADY WRITTEN when its FIRST load is refused — everything before that load,
# and `load_resource_by_index`'s own two arms. Stated per slice rather than as one list, because the
# three do different amounts of work before they ask for a file, and that difference is the point:
# the stage slice has consumed a sequence row by then and the title slice has armed the protection.
_STOPPED_BANDS = {
    "boot_title_screen": ((COPYLOCK_ARM_FLAG, COPYLOCK_ARM_FLAG_LEN),),        # $e51e's arming
    "boot_credits_screen": (),                                                 # nothing at all
    # ...nor this one: the clear and the base publish ahead of its load are both off the image.
    "boot_prompt_screen": (),
    "boot_load_stage": ((wb("ACTOR_PLATFORM_RIDDEN"), WORD_LEN),               # ...and $e5ba's
                        (LEVEL_SEQ_INDEX, WORD_LEN),                           #    three stores
                        (wb("STAGE_SECOND_LOAD_FLAG"), 1)),
}
# `load_resource_by_index`'s own, on every slice: the two retry longwords it writes before the call,
# the `clr.b` its error arm makes, and WB_FLOPPY_IDLE_TIMER — the driver's idle fuse, which the seam
# disarms for the load and re-arms on the way out of BOTH arms, this one included (test_boot.py pins
# all three).
_LOAD_BANDS = ((LOAD_RETRY_INDEX, LONGWORD_LEN), (LOAD_RETRY_DEST, LONGWORD_LEN),
               (wb("JOY1_STATE"), 1), (FLOPPY_IDLE_TIMER, WORD_LEN))
# ...and the byte each slice must be SHOWN to have written before it asked for the file. The bands
# above are permissions, and a permission is not evidence: a port that reported the error before
# doing any of the pre-load work would satisfy every one of them. Each entry names an address whose
# value the shipped image does NOT already hold, so the change is observable — WB_ACTOR_PLATFORM_
# RIDDEN and WB_STAGE_SECOND_LOAD_FLAG are deliberately absent for exactly that reason, both being
# already zero and written zero.
_STOPPED_EVIDENCE = {
    "boot_title_screen": (COPYLOCK_ARM_FLAG, COPYLOCK_ARM_FLAG_LEN),   # $e51e armed the protection
    "boot_credits_screen": None,                                       # it does nothing beforehand
    # ...and this one does two things beforehand, NEITHER of which an image byte can witness — a
    # palette clear and a screen-base publish, both to registers off the loaded image. So its
    # refusal case is bounded and has no positive evidence to offer, which is said rather than
    # papered over: what the run above pins is that the slice stops, not where it stopped from.
    "boot_prompt_screen": None,
    "boot_load_stage": (LEVEL_SEQ_INDEX, WORD_LEN),                    # $e5cc stepped the sequence
}
# ...and WHAT THE FLAG IS LEFT HOLDING, which is a residue and not a permission. `load_resource_by_
# index` clears WB_COPYLOCK_ARM_FLAG on exactly one path — the load that was armed AND was served —
# and its error return never touches it, so a refused load the slice had ARMED comes back with the
# flag still set. That is a caller's problem (src/boot.c's `load_or_stop` banner states the retry
# contract it creates) and it is asserted here rather than described, because the band above merely
# PERMITS the address: a port that armed and then disarmed on the way out would satisfy it.
# True = the slice armed before the load this case refuses.
_STOPPED_ARMED = {"boot_title_screen": True,        # $e51e arms, and the refused load is that one
                  "boot_credits_screen": False,     # nothing on this slice ever arms
                  "boot_prompt_screen": False,      # ...nor this one
                  "boot_load_stage": False}         # the FIRST load is refused; $e6dc is far past it


def _changed_addresses(before, after):
    return [at for at, (b, a) in enumerate(zip(bytes(before), bytes(after))) if a != b]


def _arm_flag(image):
    return bytes(image[COPYLOCK_ARM_FLAG:COPYLOCK_ARM_FLAG + COPYLOCK_ARM_FLAG_LEN])


def _assert_arm_flag_residue(name, armed, before, after):
    """A refusal leaves WB_COPYLOCK_ARM_FLAG exactly where the slice put it: ARMED if the refused
    load was one the slice had armed, and untouched otherwise. The unarmed side is compared against
    the SHIPPED image's own byte rather than against a written-down zero, so this stays a statement
    about the slice and not about the .PRG's contents."""
    want = copylock.ARMED if armed else _arm_flag(before)
    why = ("an armed load that the seam refused stays armed" if armed
           else "this path arms nothing, so the flag is the shipped image's own")
    assert _arm_flag(after) == want, (
        f"{name} left copylock_arm_flag at {_arm_flag(after).hex()} after the refusal, and it "
        f"should be {want.hex()}: {why}")


@pytest.mark.parametrize("name", sorted(_STOPPED_BANDS))
def test_a_slice_whose_load_the_seam_refuses_stops_where_the_original_waits_for_fire(name):
    """CANDIDATE-ONLY, and it says so: the kit's file model serves a call or REFUSES it, and a
    refusal sinks the oracle run before any comparison happens (test_boot.py's error-arm cases carry
    the same caveat and ../STATUS.md the same kit-side remedy). What is compared here is the port
    against the original's own control flow: the original sits in `load_resource_by_index`'s
    interactive retry, so a port that carried on would be inflating a buffer the file never arrived
    in.

    THE CLAIM IS THE WHOLE IMAGE, not the destination. An earlier revision of this case asserted only
    that the depack destination was untouched, and a mutant that deleted the stop SURVIVED it: a
    `rad_depack` handed the refused load's ZEROED buffer reads an unpacked length of 0 and fills
    BACKWARDS from the destination, so the four bytes AT the destination are the only ones in the
    region it does not write. Every byte that changed is enumerated instead, and the run may change
    nothing the slice had not already written when it asked for the file.

    THE PREMISE IS THE REFUSAL, staged by staging NOTHING, and the control below is what says the
    refusal is doing the work.
    """
    before = harness.make_image({})
    ret, after = leaf.run_candidate_only(_slice_glue(name, park=False), {})
    assert ret == LOAD_DISK_ERROR, (
        f"{name} with nothing staged returned {ret}, not WB_LOAD_DISK_ERROR")
    changed = _changed_addresses(before, after)
    stray = leaf.stray_writes(changed, list(_STOPPED_BANDS[name]) + list(_LOAD_BANDS))
    assert not stray, (
        f"{name} changed {len(stray)} byte(s) it had not already written when the seam refused "
        f"its load, e.g. {harness.label(stray[0])} @ {stray[0]:#x} — it did not stop there")
    _assert_arm_flag_residue(name, _STOPPED_ARMED[name], before, after)
    evidence = _STOPPED_EVIDENCE[name]
    if evidence is not None:
        at, length = evidence
        # INTERSECTS rather than covers: a word store can leave one of its two bytes equal (the
        # sequence index steps $0001 -> $0002 and only the low byte moves), so requiring the whole
        # band would fail on a correct port.
        assert set(range(at, at + length)) & set(changed), (
            f"{name} reported the error without touching {harness.label(at)} @ {at:#x} — it stopped "
            f"BEFORE the work the slice does ahead of its first load, not at the load")


# THE STAGE SLICE HAS THREE STOPS AND THE CASE ABOVE DRIVES ONE. Each row is (which files to stage,
# the last thing the slice produced BEFORE the refused load, the first thing it would have produced
# AFTER it, and whether the protection was armed for the load that was refused) — so a stop is
# pinned by what is on both sides of it rather than by the return code alone. The addresses are the
# slice's own depack destinations and install products. Only the THIRD load is armed ($e6dc, inside
# the second-load gate), and its refusal is therefore the one that leaves the flag standing.
_STAGE_STOPS = {
    "the overlay": ([], None, wb("OVERLAY_DEPACK_DEST"), False),
    "TILEDATA.RAD": (["overlay"], wb("OVERLAY_DEPACK_DEST"), wb("TILE_BANK"), False),
    "SPRITES.CRU": (["overlay", "tiledata"], wb("TILE_BANK"), wb("SPRITE_CRU_CELLS"), True),
}


@pytest.mark.parametrize("refused", sorted(_STAGE_STOPS))
def test_the_stage_slice_stops_at_whichever_of_its_three_loads_is_refused(refused):
    """CANDIDATE-ONLY, for the refusal case's reason. What it adds is that the slice's OTHER TWO
    stops exist: staging the overlay but not TILEDATA leaves the run at the second load, and staging
    both but not SPRITES.CRU leaves a FIRST ENTRY at the third — with the protection already armed
    and consumed, the tile bank installed and the resource table restored. Neither had a case, and a
    port that dropped either stop would have gone on inflating a buffer that never arrived.

    Each row asserts BOTH SIDES of its stop: the product before it is there, and the product after
    it is not — plus the RESIDUE the stop leaves on WB_COPYLOCK_ARM_FLAG, which is what makes the
    SPRITES.CRU stop different in kind from the other two."""
    staged, before_at, after_at, armed = _STAGE_STOPS[refused]
    name, overlay = _overlay_of(0)
    files = ([(name, overlay)] if "overlay" in staged else [])
    if "tiledata" in staged:
        files.append(("TILEDATA.RAD", TILEDATA.read_bytes()))
    poison = bytes([POISON]) * LONGWORD_LEN
    pokes = {**(seam_pokes(files) if files else {}),
             LEVEL_SEQ_INDEX: (0).to_bytes(WORD_LEN, "big"),
             LIFE_RESTART_ENTRY_C26: (0).to_bytes(WORD_LEN, "big"),
             after_at: poison}
    if before_at is not None:
        pokes[before_at] = poison
    before = harness.make_image(pokes)
    ret, image = leaf.run_candidate_only(_slice_glue("boot_load_stage"), pokes)

    assert ret == LOAD_DISK_ERROR, (
        f"with {refused} unstaged the slice returned {ret}, not WB_LOAD_DISK_ERROR")
    _assert_arm_flag_residue(f"boot_load_stage / {refused}", armed, before, image)
    assert bytes(image[after_at:after_at + len(poison)]) == poison, (
        f"the slice wrote {after_at:#x} although the {refused} load was refused — it did not stop")
    if before_at is not None:
        assert bytes(image[before_at:before_at + len(poison)]) != poison, (
            f"the slice never reached {before_at:#x}, so it stopped BEFORE the {refused} load and "
            f"this case is not about the stop it names")


# (pokes, the destination the slice's FIRST depack fills) for the control below.
_SERVED_CASE = {
    "boot_title_screen": (_title_pokes, TITLE_DEPACK_DEST),
    "boot_credits_screen": (_credits_pokes, CREDITS_DEPACK_DEST),
    "boot_prompt_screen": (_prompt_pokes, CREDITS_DEPACK_DEST),
    "boot_load_stage": (lambda: _stage_pokes(0, reentry=1, sprites=False),
                        wb("OVERLAY_DEPACK_DEST")),
}


@pytest.mark.parametrize("name", sorted(_SERVED_CASE))
def test_a_slice_whose_loads_are_all_served_does_not_stop(name):
    """The control for the case above: the same three slices, with every resource they load staged,
    run to the end and write their destination. Without it each of those assertions would pass on a
    port that always reported an error."""
    build_pokes, written = _SERVED_CASE[name]
    poison = bytes([POISON]) * LONGWORD_LEN
    ret, image = leaf.run_candidate_only(_slice_glue(name), {**build_pokes(), written: poison})
    assert ret != LOAD_DISK_ERROR, f"{name} reported an error with its resources staged"
    assert bytes(image[written:written + len(poison)]) != poison, (
        f"{name} left {written:#x} untouched although its loads were served")
