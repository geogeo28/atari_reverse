#!/usr/bin/env python3
"""sysvars.py — the TOS system-variable block at $400, as ONE table every instrument here reads.

The block is the OS's published state, and three different things here need it: `boot_surface.py`
renders it by name, the boot metric reads the three clocks out of it, and `prg/tosapi.h` spells two
of the same addresses in C for the programs that run on the machine. Three spellings of `$4BA` is
two chances to get it wrong, so the addresses live here and `test_atari_pins.py` pins the rest:
every name against `projects/tos102us/names.txt` (the workspace's source of truth for names) and
every `SYSVAR_*` in `prg/tosapi.h` against this table's address for the same variable.

THE LAYOUT WAS VERIFIED AGAINST A BOOTED MACHINE, not copied from a reference: the three magic
longwords land where the table says (`memvalid` $752019F3 at $420, `memval2` $237698AA at $43A,
`memval3` $5555AAAA at $51A), `_vblqueue` at $456 points at `_vbl_list` at $4CE, `_v_bas_ad` at
$44E equals `_memtop`, `_drvbits` at $4C2 reads 3 for the two floppies, `swv_vec` at $46E holds the
ROM's own reset entry $FC0030 and `_sysbase` at $4F2 holds $FC0000. Two widely-published variants of
this table differ by two bytes around $44C; the one below is the one the machine agrees with.

THE TAIL IS THE ONE PART A BOOTED MACHINE CANNOT SETTLE: $59E-$5B3 reads all zeroes under TOS 1.02,
so the two published variants — one with a `prt_cnt` word at $59E and everything after it two bytes
higher, one with `_longframe` there — are indistinguishable by measurement. It follows `names.txt`,
which is the one EmuTOS's `tosvars.S` also uses.
"""

# (address, width, count, name). Width is 'B', 'W' or 'L'; count > 1 is an array. `(pad)` is a byte
# the block does not name — it is here so the table is contiguous, which is what lets the pin test
# catch an entry that silently shifted the ones after it.
SYSVARS = (
    (0x400, "L", 1, "etv_timer"),      (0x404, "L", 1, "etv_critic"),
    (0x408, "L", 1, "etv_term"),       (0x40C, "L", 5, "etv_xtra"),
    (0x420, "L", 1, "memvalid"),       (0x424, "W", 1, "memctrl"),
    (0x426, "L", 1, "resvalid"),       (0x42A, "L", 1, "resvector"),
    (0x42E, "L", 1, "phystop"),        (0x432, "L", 1, "_membot"),
    (0x436, "L", 1, "_memtop"),        (0x43A, "L", 1, "memval2"),
    (0x43E, "W", 1, "flock"),          (0x440, "W", 1, "seekrate"),
    (0x442, "W", 1, "_timr_ms"),       (0x444, "W", 1, "_fverify"),
    (0x446, "W", 1, "_bootdev"),       (0x448, "W", 1, "palmode"),
    (0x44A, "B", 1, "defshiftmd"),     (0x44B, "B", 1, "(pad)"),
    (0x44C, "W", 1, "sshiftmd"),       (0x44E, "L", 1, "_v_bas_ad"),
    (0x452, "W", 1, "vblsem"),         (0x454, "W", 1, "nvbls"),
    (0x456, "L", 1, "_vblqueue"),      (0x45A, "L", 1, "colorptr"),
    (0x45E, "L", 1, "screenpt"),       (0x462, "L", 1, "_vbclock"),
    (0x466, "L", 1, "_frclock"),       (0x46A, "L", 1, "hdv_init"),
    (0x46E, "L", 1, "swv_vec"),        (0x472, "L", 1, "hdv_bpb"),
    (0x476, "L", 1, "hdv_rw"),         (0x47A, "L", 1, "hdv_boot"),
    (0x47E, "L", 1, "hdv_mediach"),    (0x482, "W", 1, "_cmdload"),
    (0x484, "B", 1, "conterm"),        (0x485, "B", 1, "(pad)"),
    (0x486, "L", 1, "trp14ret"),       (0x48A, "L", 1, "criticret"),
    (0x48E, "L", 4, "themd"),          (0x49E, "L", 1, "_md"),
    (0x4A2, "L", 1, "savptr"),         (0x4A6, "W", 1, "_nflops"),
    (0x4A8, "L", 1, "con_state"),      (0x4AC, "W", 1, "save_row"),
    (0x4AE, "L", 1, "sav_context"),    (0x4B2, "L", 2, "_bufl"),
    (0x4BA, "L", 1, "_hz_200"),        (0x4BE, "L", 1, "the_env"),
    (0x4C2, "L", 1, "_drvbits"),       (0x4C6, "L", 1, "_dskbufp"),
    (0x4CA, "L", 1, "_autopath"),      (0x4CE, "L", 8, "_vbl_list"),
    (0x4EE, "W", 1, "_dumpflg"),       (0x4F0, "W", 1, "_prtabt"),
    (0x4F2, "L", 1, "_sysbase"),       (0x4F6, "L", 1, "_shell_p"),
    (0x4FA, "L", 1, "end_os"),         (0x4FE, "L", 1, "exec_os"),
    (0x502, "L", 1, "scr_dump"),       (0x506, "L", 1, "prv_lsto"),
    (0x50A, "L", 1, "prv_lst"),        (0x50E, "L", 1, "prv_auxo"),
    (0x512, "L", 1, "prv_aux"),        (0x516, "L", 1, "pun_ptr"),
    (0x51A, "L", 1, "memval3"),        (0x51E, "L", 8, "xconstat"),
    (0x53E, "L", 8, "xconin"),         (0x55E, "L", 8, "xcostat"),
    (0x57E, "L", 8, "xconout"),        (0x59E, "W", 1, "_longframe"),
    (0x5A0, "L", 1, "_p_cookies"),     (0x5A4, "L", 1, "ramtop"),
    (0x5A8, "L", 1, "ramvalid"),       (0x5AC, "L", 1, "bell_hook"),
    (0x5B0, "L", 1, "kcl_hook"),
)

WIDTH_BYTES = {"B": 1, "W": 2, "L": 4}
WIDTH_FORMAT = {"B": ">B", "W": ">H", "L": ">I"}

# A name the block does not use: present only so the table covers every byte between its ends.
PAD_NAME = "(pad)"

BLOCK_START = SYSVARS[0][0]
BLOCK_END = SYSVARS[-1][0] + WIDTH_BYTES[SYSVARS[-1][1]] * SYSVARS[-1][2]

# The three variables that count time, with the reason each is excluded from every comparison. They
# are masked by POLICY — a comparison of two boots has no business requiring two clocks to agree —
# and reported separately as the boot metric, which is the useful half of the same bytes.
TIME_VARYING = (
    ("_vbclock", "counts vblanks"),
    ("_frclock", "counts vblanks"),
    ("_hz_200", "counts 200ths of a second"),
)


def entry(name):
    """The (address, width, count) of one system variable, by the name this table gives it."""
    for address, width, count, entry_name in SYSVARS:
        if entry_name == name:
            return address, width, count
    raise KeyError(f"no system variable named {name} in SYSVARS")


def address_of(name):
    return entry(name)[0]


# (address, bytes, why) for every masked field — the form a comparison and a render both want.
MASKED_FIELDS = tuple((address_of(name), WIDTH_BYTES[entry(name)[1]], f"{name} {why}")
                      for name, why in TIME_VARYING)
