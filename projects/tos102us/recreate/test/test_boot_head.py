"""THE BOOT'S HEAD HELD (boot B1; rulings D7 "Byte-transcribed .S", D8, D9, "ROM-window overlay", "Own link rule"):
`src/boot/head/head.S` against the ROM's `[$fc0030, $fc02cc)` byte for byte where it is LAID, and slice by slice on
the WARM and COLD machines — ours and the ROM's from one machine, every surface held equal (`boot_head.differences`)
— with the staging's own premises and the harness's two extensions (`boot.run`'s `laid`, the pin of a region where it
is laid) each held with its negative. Every machine named is A LABELLED STAGING; so is the overlay.

WHAT NO TEST HERE PINS, BY NAME: `reset`'s effect on the chips (D6: the byte and the count alone —
`test_reset_is_on_the_count_and_the_byte_alone` shows a `nop` in its place reaches no ledger); the diagnostic
cartridge's and the reset-resident hook's arms (D2, D12: byte-pinned only, no machine here takes them); the PAL
header's sync arm (this ROM's header is US); the cold arm's sizing on an ST's memory (D1: the oracle's is flat).
"""
import re
import struct

import pytest

import harness
from harness import BASE_IMAGE, addrs, emu

import boot
import boot_head
import rom_data
import transcription
from transcription import Laid, PC_RELATIVE, Relocated

HEAD_LO, HEAD_HI, LAID_AT = boot_head.HEAD_LO, boot_head.HEAD_HI, boot_head.LAID_AT
CONSTANTS = boot_head.CONSTANTS
WORD_BYTES = boot.WORD_BYTES
NOP, RESET = 0x4e71, 0x4e70
RESET_AT = HEAD_LO + 4                                         # `reset`, after `move.w #$2700,sr`
JMP_ABSOLUTE_LONG = 0x4ef9
D16_PC_BRANCH = re.compile(r"^b\w*w (0x[0-9a-f]+)$")          # `braw`, `beqw`: a `.w` branch and its target
D16_PC_OPERAND = re.compile(r"%pc@\((0x[0-9a-f]+)\)")        # a `d16(pc)` operand and the address it names
REGION = transcription.pinned_region(HEAD_LO, HEAD_HI, boot_head.SYMBOL, laid=Laid(LAID_AT, lambda: boot_head.product()))


def _references_leaving_the_head():
    """`{extension word: (ROM target, the instruction)}`: every pc-relative operand and `.w` branch of the ROM's head
    whose target lies outside it — DERIVED from the ROM's text (`rom_data.instructions`); its displacement is the
    instruction's last word."""
    found, decoded = {}, rom_data.instructions(HEAD_LO, HEAD_HI)
    for (site, text), (after, _next) in zip(decoded, [*decoded[1:], (HEAD_HI, None)]):
        targets = D16_PC_OPERAND.findall(text) or D16_PC_BRANCH.findall(text)
        for target in (int(each, 16) for each in targets):
            if not HEAD_LO <= target < HEAD_HI:
                found[after - WORD_BYTES] = (target, text)
    return found


LEAVING = _references_leaving_the_head()
RELOCATED = {at: Relocated(PC_RELATIVE, None, f"{text}: the ROM's ${target:x} in place", in_place=True)
             for at, (target, text) in LEAVING.items()}
CODE_IN_PLACE = ("ROM_MEMVALID_CHECK", "ROM_BANK_TEST", "ROM_SYNC_WAIT")
DATA_IN_PLACE = ("ROM_OS_CONF_LOW", "ROM_BOOT_PALETTE", "ROM_OS_MAGIC", "ROM_HEADER_AS_MUPB")


# ---- THE PRODUCT AND ITS PIN --------------------------------------------------------------------------------------------
def test_the_references_leaving_the_head_are_the_ten_the_header_names():
    """DERIVED, then held to `boot/head.h`: the memory-valid check twice, the bank test three times, the sync wait, and
    the four data reads — the orchestrator's call reaches each in place, no thunk. (The RAM probe's handler,
    `lea $fc019e(pc)`, lies inside the head and is no relocation.)"""
    targets = sorted(target for target, _text in LEAVING.values())
    assert len(LEAVING) == 10
    assert set(targets) == {CONSTANTS[name] for name in CODE_IN_PLACE + DATA_IN_PLACE}
    assert targets.count(CONSTANTS["ROM_MEMVALID_CHECK"]) == 2 and targets.count(CONSTANTS["ROM_BANK_TEST"]) == 3


def test_the_product_is_linked_where_it_is_laid_and_its_cuts_are_where_the_rom_has_them():
    """`build/boothead/` (the Makefile's own rule): `boot_head` at HEAD_LAID_AT, the head's length, and each cut's
    entry where the ROM's instruction lies by offset."""
    base, held = boot_head.product()
    assert base == LAID_AT and len(held) == HEAD_HI - HEAD_LO
    symbols = boot_head.product_symbols()
    for symbol, rom_address in (("boot_head_first_ends", boot.HEAD_FIRST_ENDS), ("boot_head_cold_arm", boot.COLD_ARM),
                                ("boot_head_warm_arm", boot.WARM_ARM), ("boot_head_ends", boot.HEAD_ENDS)):
        assert symbols[symbol] == boot_head.ours(rom_address), symbol


def test_the_rom_s_second_instruction_is_reset():
    assert struct.unpack_from(">H", BASE_IMAGE, RESET_AT)[0] == RESET


def test_the_head_is_the_rom_s_bytes_where_it_is_laid():
    """THE BYTE PIN (D7): every word the ROM's but the ten that reach the ROM in place, each the exact displacement
    from where the head is laid. It is the one surface that sees `reset` itself (D6) and the arms no machine takes."""
    transcription.assert_transcribed(REGION, relocated=RELOCATED)


def test_the_pin_reds_on_a_word_of_the_product_changed(monkeypatch):
    base, held = boot_head.product()
    changed = bytearray(held)
    changed[RESET_AT - HEAD_LO:RESET_AT - HEAD_LO + WORD_BYTES] = struct.pack(">H", NOP)   # `reset` made a `nop`
    monkeypatch.setattr(boot_head, "product", lambda: (base, bytes(changed)))
    with pytest.raises(AssertionError, match=r"\$fc0034 holds 4e71 against the ROM's 4e70"):
        transcription.assert_transcribed(REGION, relocated=RELOCATED)


def test_the_pin_reds_on_a_relocation_left_out():
    left_out = dict(RELOCATED)
    left_out.pop(min(left_out))
    with pytest.raises(AssertionError, match=r"the transcription of \$fc0052 holds"):
        transcription.assert_transcribed(REGION, relocated=left_out)


@pytest.mark.parametrize("anchored", (Relocated(PC_RELATIVE, "AES_ROM_RC_INTERSECT", "measured against the bench blob"),
                                      Relocated(PC_RELATIVE, None, "a thunk of the bench blob", thunk="aes_rc_intersect")),
                         ids=("a target anchor", "a thunk"))
def test_a_laid_region_reaches_the_rom_in_place_and_nothing_else(anchored):
    """A relocation measured against a Tier 3 blob's layout, in a region pinned where it is laid, is refused."""
    with pytest.raises(AssertionError, match="pinned where it is LAID"):
        transcription.assert_transcribed(REGION, relocated={**RELOCATED, min(RELOCATED): anchored})


def test_an_in_place_reference_into_a_pinned_region_or_off_the_rom_is_refused(monkeypatch):
    """`in_place` is refused where its target is byte-pinned (a reference into a transcription must reach the
    transcription) and where it is not the ROM — the ROM's word made, by a patch of the follower, to name each."""
    at = min(RELOCATED)
    pinned = next(region for region in transcription.every_pinned_region() if region is not REGION)
    for target, refusal in ((pinned.lo, "is byte-pinned"), (addrs.ROM_BASE - WORD_BYTES, "which is not the ROM")):
        monkeypatch.setattr(transcription, "_relocation_target", lambda _at, _relocation, target=target: target)
        with pytest.raises(AssertionError, match=refusal):
            transcription.assert_transcribed(REGION, relocated={at: RELOCATED[at]})
        monkeypatch.undo()


def test_an_in_place_reference_outside_a_laid_region_is_refused_by_name():
    """...and the converse (review RB1's F4): a word of a Tier 3 blob's region reaches no ROM byte where it lies — refused
    by name, not left to the arithmetic (an ABSOLUTE one equal to the ROM's word, a PC-relative one off 16 bits)."""
    pinned = next(region for region in transcription.every_pinned_region() if not region.laid)
    in_place = {pinned.lo: Relocated(PC_RELATIVE, None, "a bench word made in place", in_place=True)}
    with pytest.raises(AssertionError, match="is in_place outside a region pinned where it is LAID"):
        transcription.assert_transcribed(pinned, relocated=in_place)


def test_a_laid_region_names_no_entries():
    with pytest.raises(AssertionError, match="names entries of a blob"):
        transcription.pinned_region(HEAD_LO, HEAD_HI, boot_head.SYMBOL, ("AES_ROM_RC_INTERSECT",), laid=REGION.laid)


# ---- THE OVERLAY: A LABELLED STAGING (ruling "ROM-window overlay") ----------------------------------------------------
def _with_the_overlay_in_the_image(monkeypatch):
    image = bytearray(BASE_IMAGE)
    staged = boot_head.overlay()
    image[staged.at:staged.at + len(staged.code)] = staged.code
    monkeypatch.setattr(boot, "BASE_IMAGE", image)


@pytest.mark.parametrize("name", boot_head.SLICES)
def test_the_rom_s_own_shore_neither_reads_nor_runs_the_span_the_head_is_laid_over(name, monkeypatch):
    """THE STAGING'S PREMISE: the ROM's own slice from the same machine, with our head laid over the span and without
    it, is the same run on every surface — so nothing of the ROM's slices reads or executes `[$fc6000, $fc629c)`."""
    head_slice = boot_head.SLICES[name]
    plain = boot_head.the_rom_s(head_slice)
    _with_the_overlay_in_the_image(monkeypatch)
    overlaid = boot_head.the_rom_s(head_slice, boot_head.start_of(head_slice))
    assert plain == overlaid


def test_an_overlay_outside_the_rom_window_odd_or_over_the_rom_s_head_is_refused():
    """...code laid above $400000 executes the oracle's zeros (measured: they slide into the ROM's own head)."""
    code = boot_head.product()[1]
    for at, refusal in ((0x400000, "outside the ROM window"), (boot.ROM_WINDOW[1] - WORD_BYTES, "outside the ROM window"),
                        (LAID_AT + 1, "odd address"), (HEAD_LO, "over the ROM's own head")):
        with pytest.raises(boot.Refused, match=refusal):
            boot.overlaid(at, code)


def test_the_overlay_says_what_is_laid_and_what_is_real():
    staged = boot_head.overlay()
    assert (staged.at, staged.code) == boot_head.product()
    assert "LABELLED STAGING" in staged.label and f"{LAID_AT:#x}" in staged.label and "REAL" in staged.label


def test_a_run_of_ours_that_executes_the_rom_s_own_head_is_refused_by_name():
    """THE FALSE GREEN (the user's ruling): code of ours that falls into the ROM's head would run the ROM's own
    instructions and be measured equal. A head that `jmp`s to the reset is run to the ROM's own first cut — and
    refused, read off the run's profile."""
    jump = struct.pack(">HI", JMP_ABSOLUTE_LONG, boot.RESET_PC).ljust(HEAD_HI - HEAD_LO, b"\0")
    machine = boot_head.ours_of(boot.warm_machine())
    with pytest.raises(boot.Refused, match=r"executed the ROM's own head \[0xfc0030, 0xfc02cc\)"):
        boot.run(machine, {boot.HEAD_FIRST_ENDS, boot_head.ours(boot.HEAD_FIRST_ENDS)}, laid=boot_head.overlay(jump))


@pytest.mark.parametrize("into", (boot.RESET_PC, boot.WARM_ARM, boot.LEA_STACK), ids=hex)
def test_a_run_of_ours_that_falls_anywhere_into_the_rom_s_head_is_refused(into):
    """...ITS WHOLE SPAN (review RB1's F1: a guard that watched only `[$fc0030, $fc0038)` passed every test above): a
    head of ours that jumps to the reset, to the warm arm or to the `lea $755a,sp` at the span's end is refused."""
    jump = struct.pack(">HI", JMP_ABSOLUTE_LONG, into).ljust(HEAD_HI - HEAD_LO, b"\0")
    machine = boot_head.ours_of(boot.warm_machine())
    with pytest.raises(boot.Refused, match="executed the ROM's own head"):
        boot.run(machine, {boot.HEAD_FIRST_ENDS, boot.HEAD_ENDS, boot_head.ours(boot.HEAD_FIRST_ENDS)},
                 laid=boot_head.overlay(jump))


def test_a_run_of_ours_kept_to_its_own_head_is_not_refused():
    """...and its negative: our own head's run, with the ROM's cut also armed, arrives at ours alone."""
    machine = boot_head.ours_of(boot.warm_machine())
    done = boot.run(machine, {boot.HEAD_FIRST_ENDS, boot_head.ours(boot.HEAD_FIRST_ENDS)}, laid=boot_head.overlay())
    assert done.stop == boot_head.ours(boot.HEAD_FIRST_ENDS)
    assert emu.prof_cycles(LAID_AT, LAID_AT + HEAD_HI - HEAD_LO) > 0


# ---- THE SLICES, BOTH SHORES ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", boot_head.SLICES)
def test_each_slice_of_ours_is_the_rom_s_on_every_surface(name):
    """D7's comparison: our slice and the ROM's from one machine (the ROM's own at the slice's start) — the stop and
    the registers by offset (the PC, A6), the megabyte, the addresses stored, every ordered ledger, the instruction
    count and the cycles."""
    head_slice = boot_head.SLICES[name]
    the_rom_s, ours = boot_head.the_rom_s(head_slice), boot_head.our_side(head_slice)
    assert boot_head.differences(the_rom_s, ours) == []
    assert ours.stop == boot_head.ours(head_slice.cut.stop)


def test_the_cold_arm_sizes_the_oracle_s_flat_megabyte_d1():
    """D1 BITES HERE, NAMED: the cold arm's sizing on the oracle's flat memory — 1 MB and memctrl $08, both shores —
    deterministic and not an ST's answer (the snapshot's machine holds $05)."""
    priced = boot_head.priced(boot_head.SLICES[f"boot head {boot_head.H2.name}, {boot.COLD}"])
    for shore in (priced.the_rom_s, priced.ours):
        ram = shore.machine.ram
        assert ram[CONSTANTS["SYSVAR_MEMCTRL"]] == 0x08
        assert struct.unpack_from(">I", ram, addrs.SYSVAR_PHYSTOP)[0] == boot.RAM_BYTES


def test_the_warm_arm_s_sizing_is_fourteen_instructions():
    priced = boot_head.priced(boot_head.SLICES[f"boot head {boot_head.H2.name}, {boot.WARM}"])
    assert priced.the_rom_s.instructions == priced.ours.instructions == 14


def test_reset_is_on_the_count_and_the_byte_alone():
    """D6, OPEN AND SAID: Musashi takes `reset` as a no-op. A head with a `nop` in its place differs from the ROM's
    on its cycles alone — one instruction each, no ledger moved: the chips' reset is on no surface; the byte pin is
    what holds the instruction."""
    code = bytearray(boot_head.product()[1])
    code[RESET_AT - HEAD_LO:RESET_AT - HEAD_LO + WORD_BYTES] = struct.pack(">H", NOP)
    head_slice = boot_head.SLICES[f"boot head {boot_head.H1.name}, {boot.WARM}"]
    found = boot_head.differences(boot_head.the_rom_s(head_slice), boot_head.our_side(head_slice, code=bytes(code)))
    assert [each.split(":")[0] for each in found] == ["cycles"]


# ---- THE COMPARATOR'S OWN NEGATIVES: each surface, changed alone, is named ----------------------------------------------
@pytest.fixture(scope="module")
def a_pair():
    head_slice = boot_head.SLICES[f"boot head {boot_head.H1.name}, {boot.WARM}"]
    return boot_head.the_rom_s(head_slice), boot_head.our_side(head_slice)


def _flipped_ram(ram):
    changed = bytearray(ram)
    changed[CONSTANTS["HEAD_CLEAR_LO"]] ^= 1
    return bytes(changed)


def _changed(ours, surface):
    """`ours` with `surface` alone made to differ."""
    if surface == "registers":
        return ours._replace(machine=ours.machine._replace(registers={**ours.machine.registers, "d7": 1}))
    if surface == "ram":
        return ours._replace(machine=ours.machine._replace(ram=_flipped_ram(ours.machine.ram)))
    if surface == "stop":
        return ours._replace(stop=ours.stop + WORD_BYTES)
    if surface in ("instructions", "cycles"):
        return ours._replace(**{surface: getattr(ours, surface) + 1})
    if surface == "faults":
        return ours._replace(faults={0: b"\0"})
    return ours._replace(**{surface: (*getattr(ours, surface), ("a difference",))})


# THE SURFACES D7's comparison holds, spelt here and not read off the comparator: a surface dropped from
# `boot_head.SURFACES` would otherwise take its own negative with it (the mutation sweep's two survivors).
HELD = ("stop", "registers", "ram", "stored", "hardware_writes", "io_reads", "hardware_reads", "psg_events", "faults",
        "instructions", "cycles")


def test_the_comparator_holds_every_surface():
    assert boot_head.SURFACES == HELD


@pytest.mark.parametrize("surface", HELD)
def test_each_surface_differing_alone_is_named(a_pair, surface):
    the_rom_s, ours = a_pair
    assert boot_head.differences(the_rom_s, ours) == []
    found = boot_head.differences(the_rom_s, _changed(ours, surface))
    assert len(found) == 1 and found[0].startswith(surface), found


def test_a_link_left_where_the_rom_has_it_is_a_difference(a_pair):
    """A6 BY OFFSET, not by value: our run's return link equal to the ROM's own address is a head of ours that
    returned through the ROM's (here, staged by hand) — named, as the PC's would be."""
    the_rom_s, ours = a_pair
    assert boot_head.in_the_head(the_rom_s.machine.registers["a6"])
    unmapped = ours._replace(machine=ours.machine._replace(registers={**ours.machine.registers,
                                                                      "a6": the_rom_s.machine.registers["a6"]}))
    found = boot_head.differences(the_rom_s, unmapped)
    assert len(found) == 1 and "'a6'" in found[0]


# ---- ITS PRICE (ruling D9): the table's six rows ------------------------------------------------------------------------
def test_the_table_prices_each_slice_on_each_shore_s_own_cycles():
    """`bench/tier3.py`'s boot-slice rows: one per slice, each a STRETCH between two cuts — its costs each shore's
    whole instruction count and OWN cycles (the head's PCs), the ROM's code both run in place held equal and printed
    beneath, its ratio 1.00 and its verdict `ok`."""
    tier3 = harness.bench_tier3()
    rows = [row for row in tier3.ROWS if tier3.is_a_boot_slice(row)]
    assert [row.registered for row in rows] == list(boot_head.SLICES)
    bench = tier3.RomBench()
    for row in rows:
        priced, measured = boot_head.priced(boot_head.SLICES[row.registered]), tier3.measure(row, bench)
        own_ours, own_the_rom_s = priced.own
        assert tier3._costs(measured) == ((priced.the_rom_s.instructions, own_the_rom_s), (priced.ours.instructions, own_ours))
        assert measured.boot_rest == priced.rest and measured.ratio == 1.0
        assert tier3.verdict(row, measured, 0, None) == "ok"


class _OursOwnReadShort:
    """`emu` with our head's own cycles read 4 short of what the run spent: the code both run then differs by 4."""

    def __getattr__(self, name):
        return getattr(emu, name)

    @staticmethod
    def prof_cycles(lo, hi):
        return emu.prof_cycles(lo, hi) - (4 if lo == LAID_AT else 0)


def test_the_code_both_shores_run_is_held_equal_in_the_price(monkeypatch):
    """`priced`'s own refusal: the cycles beside each shore's own (the ROM's code run in place, the entry) differ —
    staged by reading our own 4 cycles short — and the slice is refused by name, whatever its whole runs say."""
    monkeypatch.setattr(boot_head, "emu", _OursOwnReadShort())
    with pytest.raises(AssertionError, match="the code both run cost ours"):
        boot_head.priced(boot_head.SLICES[f"boot head {boot_head.H1.name}, {boot.WARM}"])
