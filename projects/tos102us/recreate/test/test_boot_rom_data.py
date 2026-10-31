"""EVERY ROM ADDRESS THE BOOT USES AS A VALUE — enumerated, and held to its source (boot B1, B2).

The census, its KINDS and what each owes a rebuilt ROM are `rom_data.py`'s; this is the boot's table, over
`src/boot/head/head.S` and `include/boot/` (the head lies one directory below kit.mk's sweep: the Makefile's own rule
links it, `build/boothead/`) and over `src/boot/` (B2's C and its entry, in the sweep: the bench blob). D11 IS OPEN
(ROM data by ROM address vs `data/`): each TABLE here is read where it lies, as the orchestrator's call has it, and
stands as an obligation on a rebuilt ROM — nothing is extracted.

`test_the_census_is_the_list` is the surface: a new use of a ROM address in the boot's sources (`src/boot/`, the head
among them) reds until it is listed with its kind, and a listed one the source no longer makes reds too; `test_a_table_s_kind_is_where_it_lies` holds each TABLE
outside every byte-pinned region.
"""
import rom_data
from rom_data import CODE, TABLE

BOOT = rom_data.Component(rom_data.RECREATE / "src" / "boot" / "head", rom_data.INCLUDE / "boot")
BOOT_C = rom_data.Component(rom_data.RECREATE / "src" / "boot", rom_data.INCLUDE / "boot")
SCOPES = (BOOT, BOOT_C)
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
    # B2 (`src/boot/sysvars.c`): the OS header and the device tables' defaults read in place (D11: obligations, nothing
    # extracted); the ROM's code stored by value where this build links none — the bare `rte` and `rts`, the bombs
    # handler (unported: the BIOS's exception group), the critical-error default (unported, four bytes).
    "sysvars.c": {
        "ROM_OS_HEADER": TABLE, "ROM_XCON_TABLES": TABLE,
        "ROM_BARE_RTE": CODE, "ROM_BARE_RTS": CODE, "ROM_BOMBS_ENTRY": CODE, "ROM_ETV_CRITIC_DEFAULT": CODE,
        # ...and the five handlers this build DOES link, named OFF TARGET ONLY (`BOOT_LINKED_ENTRY`): the host links no
        # entry, so its C stores the ROM's address; on target each vector holds the linked entry — no obligation left.
        "ISR_HBL": CODE, "ISR_VBL": CODE, "BIOS_TRAP13": CODE, "XBIOS_TRAP14": CODE, "LINEA_ROM_DISPATCH": CODE,
    },
    # ...and its entry's way on: the ROM's `bsr $fc2408` (B3's: the BIOS's hardware init, unported).
    "sysvars_entry.S": {"ROM_BOOT_HARDWARE_INIT_CALL": CODE},
}


def census():
    """`{file: {token}}`: every ROM address the boot's sources or its headers use as a value."""
    found = {}
    for scope in SCOPES:
        found.update(rom_data.census(scope))
    return found


def test_the_census_is_the_list():
    assert census() == rom_data.listed(ROM_ADDRESSES_AS_DATA)


def test_a_table_s_kind_is_where_it_lies():
    """A TABLE lies outside every byte-pinned region (the head's own region among them)."""
    for scope in SCOPES:
        scanned = scope.scanned()
        assert rom_data.kind_mismatches(scope, {key: uses for key, uses in ROM_ADDRESSES_AS_DATA.items()
                                                if key in scanned}) == []


def test_the_scope_is_the_boot_s_sources_and_headers():
    """The census reads the files it means — a scope one directory off would census nothing and pass."""
    assert sorted(BOOT.scanned()) == ["boot/head.h", "boot/sysvars.h", "head.S"]
    assert sorted(BOOT_C.scanned()) == ["boot/head.h", "boot/sysvars.h", "sysvars.c", "sysvars_entry.S"]
