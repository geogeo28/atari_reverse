"""geminit's two event-free LEAVES (`src/aes/geminit.c`): ini_dlongs `$fd9ffc` and pinit `$fda3d6`. (all_run, the
third, leaves by the dispatcher: `test_aes_all_run.py`.)

    ini_dlongs():    ad_shcmd = &THEGLO[8022]; ad_shtail = &THEGLO[10198]; ad_path = &THEGLO[7910];
                     ad_sysglo = &THEGLO[7992]; ad_windspb = &wind_spb
    pinit(pd, cda):  pd->p_cda = cda; pd->p_qaddr = &pd->p_queue[0]; pd->p_qindex = 0; bfill(8, ' ', pd->p_name)

WHAT REACHES EACH TODAY. Both run only while GEM starts (gem_main `$fda070`, `$fda148`) or an accessory is loaded
(`$fe451a`), and the boot snapshot is taken after both:

  * ini_dlongs READS NOTHING — five stores of constants — so the machine it runs over decides nothing; its case is
    the snapshot with the five longwords staged STALE, and what the ROM's run leaves is held to WHAT THE BOOT'S OWN
    ini_dlongs LEFT IN THE SNAPSHOT.
  * pinit is run with THE ARGUMENTS ITS ROM CALLERS PASS — gem_main's three (`pd[i]`, `cda[i]`: `$fda124..$fda148`),
    and a PD and a CDA in a block of their own, as the accessory allocator's (`$fe44d4`: one Malloc block) — over
    the post-init machine: AN ARGUMENT CLASS (the surrounding state is not the init's own: the three static PDs
    are in use). It reads nothing but its two arguments either. OWED on the pre-init and the accessory machines:
    both callers' own runs (`$fda148`, `$fe451a`).
"""
import pytest

from harness import BASE_IMAGE

import aes
import case
import vdi

INI_DLONGS, PINIT = "AES_ROM_INI_DLONGS", "AES_ROM_PINIT"
aes.declare_alcyon(INI_DLONGS, None, (vdi.IMAGE_ARG,))
aes.declare_alcyon(PINIT, None, (vdi.IMAGE_ARG, vdi.LONG_ARG, vdi.LONG_ARG))
GEMINIT = aes.header_constants("geminit.h")
WM = aes.header_constants("wmupdate.h")
OBJECTS = aes.header_constants("objects.h")
THROUGH = pytest.mark.parametrize("through_line_f", (False, True), ids=("direct", "through Line-F"))

# ---- ini_dlongs -----------------------------------------------------------------------------------------------------
# The five pointers, in the ROM's order of stores, and what each is pointed at.
POINTERS = {
    "the shell's command line": (aes.AES_SHELL_BUFFER, GEMINIT["AES_SHELL_LINE"]),
    "its tail": (aes.AES_SHELL_TAIL, aes.AES_SH_COMMAND),
    "the working path": (aes.AES_SH_PATH_POINTER, aes.AES_SH_PATH_BUFFER),
    "the AES's own global[]": (OBJECTS["AES_RS_SYSTEM_GLOBAL"], GEMINIT["AES_SYSTEM_GLOBAL"]),
    "the screen's lock": (WM["AES_AD_WINDSPB"], WM["AES_WIND_SPB"]),
}
for _what, (_at, _target) in POINTERS.items():
    aes.declare_case_field(_at, aes.LONG_BYTES, f"ini_dlongs' pointer to {_what}")
STALE_POINTERS = {at: vdi.STALE_LONG.to_bytes(aes.LONG_BYTES, "big") for at, _target in POINTERS.values()}


def dlongs_machine():
    return aes.leaf_machine(onto=STALE_POINTERS)


@THROUGH
def test_ini_dlongs_points_the_five_long_pointers(through_line_f):
    result = aes.run_function(INI_DLONGS, (), dlongs_machine(), through_line_f=through_line_f)
    assert {what: result.long(at) for what, (at, _target) in POINTERS.items()} == {
        what: target for what, (_at, target) in POINTERS.items()}


def test_what_ini_dlongs_stores_is_what_the_boot_s_own_left_in_the_snapshot():
    """THE ROM-RUN STATE: the capture's five longwords — which the boot's own ini_dlongs wrote and nothing rewrites —
    are exactly what its run stores over stale ones, and it stores nothing else (the Line-F mask word aside)."""
    result = aes.run_function(INI_DLONGS, (), dlongs_machine())
    stored = case.written_by(result.info["writes"])
    spans = {at + offset for at, _target in POINTERS.values() for offset in range(aes.LONG_BYTES)}
    assert set(stored) - {aes.AES_LINEF_MASK_WORD, aes.AES_LINEF_MASK_WORD + 1} == spans
    assert all(result.long(at) == case.long_in(BASE_IMAGE, at) for at, _target in POINTERS.values())


def test_the_pointers_lie_where_the_rom_s_displacements_put_them():
    """`lea 8022(a5)`, `10198(a5)`, `7910(a5)`, `7992(a5)` off THEGLO ($fda004 movea.l #$9c58,a5), and `#$9aee`."""
    assert [target - aes.AES_THEGLO for _at, target in list(POINTERS.values())[:4]] == [8022, 10198, 7910, 7992]
    assert list(POINTERS.values())[4][1] == 0x9AEE


# ---- pinit ------------------------------------------------------------------------------------------------------------
PD_FILL = 0x5C                          # a PD's bytes before pinit: nothing pinit stores (0, a blank, an address)
BLANK_NAME = b" " * aes.PD_NAME_BYTES
# A PD and a CDA in a block of their own (the accessory allocator's class): the staged blocks' band.
BLOCK_PD = aes.BLOCKS_AT
BLOCK_CDA = BLOCK_PD + aes.PD_BYTES
assert BLOCK_CDA + aes.CDA_BYTES <= aes.BLOCKS_AT + aes.BLOCKS_BYTES
ARGUMENT_CLASS = "ARGUMENT CLASS (its ROM caller's arguments over the post-init machine)"


def static(index):
    """gem_main's arguments of its `index`-th call ($fda124..$fda148): `&pd[index]`, `&cda[index]`."""
    return aes.AES_PD_TABLE + index * aes.PD_BYTES, aes.AES_CDA_TABLE + index * aes.CDA_BYTES


CALLS = {
    f"{ARGUMENT_CLASS}: gem_main's first, the shell's PD": static(0),
    f"{ARGUMENT_CLASS}: gem_main's second, the screen manager's": static(1),
    f"{ARGUMENT_CLASS}: gem_main's third, the spare PD": static(2),
    f"{ARGUMENT_CLASS}: a PD and a CDA in one block, the accessory allocator's": (BLOCK_PD, BLOCK_CDA),
    f"{ARGUMENT_CLASS}: the PD on the bus, the CDA with a top byte": (BLOCK_PD | aes.BUS_TAG, BLOCK_CDA | aes.BUS_TAG),
}


def pd_machine(pd):
    """The leaf machine with the PD at `pd` (as the bus carries it) FILLed whole: a field pinit left alone shows."""
    return aes.leaf_machine(onto={pd & aes.OS_BUS_ADDR_MASK: bytes([PD_FILL]) * aes.PD_BYTES})


@THROUGH
@pytest.mark.parametrize("label", CALLS)
def test_pinit_sets_the_cda_the_pipe_and_a_blank_name_and_nothing_else(label, through_line_f):
    pd, cda = CALLS[label]
    at = pd & aes.OS_BUS_ADDR_MASK
    result = aes.run_function(PINIT, (pd, cda), pd_machine(pd), through_line_f=through_line_f)
    assert result.long(at + aes.PD_CDA) == cda, "the CDA as handed, its top byte too"
    assert result.long(at + aes.PD_QUEUE_ADDRESS) == pd + aes.PD_QUEUE, "the pipe: the PD's own queue, by the pointer handed"
    assert result.word(at + aes.PD_QUEUE_INDEX) == 0
    assert result.after(at + aes.PD_NAME, aes.PD_NAME_BYTES) == BLANK_NAME
    stored = (*range(aes.PD_NAME, aes.PD_NAME + aes.PD_NAME_BYTES), *range(aes.PD_CDA, aes.PD_CDA + aes.LONG_BYTES),
              *range(aes.PD_QUEUE_ADDRESS, aes.PD_QUEUE_INDEX + aes.WORD_BYTES))
    assert all(result.final[at + offset] == PD_FILL for offset in range(aes.PD_BYTES) if offset not in stored)


def test_what_pinit_leaves_is_what_the_snapshot_s_spare_pd_still_holds():
    """THE ROM-RUN STATE: the spare static PD was pinit'd by the boot's own gem_main and never started — its CDA,
    its pipe's address and index and its blank name are, in the capture, what pinit's run over a filled PD leaves."""
    pd, cda = static(2)
    result = aes.run_function(PINIT, (pd, cda), pd_machine(pd))
    for field, size in ((aes.PD_NAME, aes.PD_NAME_BYTES), (aes.PD_CDA, aes.LONG_BYTES),
                        (aes.PD_QUEUE_ADDRESS, aes.LONG_BYTES), (aes.PD_QUEUE_INDEX, aes.WORD_BYTES)):
        assert result.after(pd + field, size) == bytes(BASE_IMAGE[pd + field:pd + field + size]), f"PD + {field}"


# ---- the registry -----------------------------------------------------------------------------------------------------
aes.register("the five pointers", INI_DLONGS, (), dlongs_machine())
for _label, (_pd, _cda) in CALLS.items():
    aes.register(_label, PINIT, (_pd, _cda), pd_machine(_pd))
