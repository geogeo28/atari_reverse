"""EVERY ROM ADDRESS THE BOOT'S HEAD USES AS A VALUE — enumerated, and held to its source (boot B1).

The census, its KINDS and what each owes a rebuilt ROM are `rom_data.py`'s; this is the boot's table, over
`src/boot/head/head.S` and `include/boot/` (the head lies one directory below kit.mk's sweep: the Makefile's own rule
links it, `build/boothead/`). D11 IS OPEN (ROM data by ROM address vs `data/`): each TABLE here is read where it lies,
as the orchestrator's call has it, and stands as an obligation on a rebuilt ROM — nothing is extracted.

`test_the_census_is_the_list` is the surface: a new use of a ROM address in the head reds until it is listed with its
kind, and a listed one the source no longer makes reds too; `test_a_table_s_kind_is_where_it_lies` holds each TABLE
outside every byte-pinned region.
"""
import rom_data
from rom_data import CODE, TABLE

BOOT = rom_data.Component(rom_data.RECREATE / "src" / "boot" / "head", rom_data.INCLUDE / "boot")
ROM_ADDRESSES_AS_DATA = {
    "head.S": {
        # Read in place, pc-relative (the four DATA operands `transcription.Relocated(..., in_place=True)` pins): the
        # header's os_conf byte, its os_magic, the header read as a MUPB, and the boot palette.
        "ROM_OS_CONF_LOW": TABLE, "ROM_OS_MAGIC": TABLE, "ROM_HEADER_AS_MUPB": TABLE, "ROM_BOOT_PALETTE": TABLE,
        # Reached in place by `bra.w`, returning through the link the head leaves: ROM code no transcription holds yet,
        # which a rebuilt ROM must link and the branch reach where it is linked.
        "ROM_MEMVALID_CHECK": CODE, "ROM_BANK_TEST": CODE, "ROM_SYNC_WAIT": CODE,
        # Stored by value in the disk, printer and screen-dump vectors: the routines' linked addresses on a rebuilt ROM.
        "ROM_HDV_INIT": CODE, "ROM_HDV_RW": CODE, "ROM_HDV_BPB": CODE, "ROM_HDV_MEDIACH": CODE, "ROM_HDV_BOOT": CODE,
        "XCOSTAT_PRT": CODE, "XCONOUT_PRT": CODE, "XCOSTAT_RS232": CODE, "XCONOUT_RS232": CODE, "ROM_SCR_DUMP": CODE,
    },
}


def census():
    """`{file: {token}}`: every ROM address the head's source or the boot's headers use as a value."""
    return rom_data.census(BOOT)


def test_the_census_is_the_list():
    assert census() == rom_data.listed(ROM_ADDRESSES_AS_DATA)


def test_a_table_s_kind_is_where_it_lies():
    """A TABLE lies outside every byte-pinned region (the head's own region among them)."""
    assert rom_data.kind_mismatches(BOOT, ROM_ADDRESSES_AS_DATA) == []


def test_the_scope_is_the_head_s_source_and_the_boot_s_header():
    """The census reads the files it means — a scope one directory off would census nothing and pass."""
    assert sorted(BOOT.scanned()) == ["boot/head.h", "head.S"]
