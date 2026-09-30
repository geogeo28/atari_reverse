"""THE ROUTINE NAMING RULE, for every component whose routine addresses carry a `ROM_` (`addrs.h`'s VDI and AES blocks).

`<COMPONENT>_ROM_<X>` is a ROUTINE's address; the same name without the `ROM_` is data or a field. The `ROM_` is not
decoration: the kit's `os.h` already owns `VDI_<FN>` and `AES_<FN>` as the OPCODES its game model serves. The C core
is the name less its `ROM_`, lower-cased (`AES_ROM_OB_OFFSET` -> `aes_ob_offset`), so both directions are a case
change and nothing is guessed — `test/vdi.py`, `test/aes.py` and `bench/tier3.py` all derive their symbols here. A `.S`
transcription KEEPS the `rom_` (`vdi_rom_vsf_perimeter`, `linea_rom_hline`, `test/transcription.py`), so its symbol is
the routine name lower-cased. Of the VDI's names, a VDI FUNCTION is the `VDI_ROM_<FN>` with an `_OPCODE` sibling.
"""
ROM_INFIX = "ROM_"
VDI_PREFIX = "VDI_ROM_"
LINEA_PREFIX = "LINEA_ROM_"
AES_PREFIX = "AES_ROM_"
# Each prefix, the component it names, and whether a Tier 3 label keeps the core's own prefix: a Line-A primitive's
# (`Line-A linea_hline`) does, a function's (`VDI vsl_type`, `AES ob_offset`) is its component's word instead.
ROLE_OF_PREFIX = {VDI_PREFIX: ("VDI", False), LINEA_PREFIX: ("Line-A", True), AES_PREFIX: ("AES", False)}
PREFIXES = tuple(ROLE_OF_PREFIX)
VDI_COMPONENT_PREFIXES = (VDI_PREFIX, LINEA_PREFIX)     # the VDI's two: its functions and helpers, and Line-A's


def prefix_of(name):
    """The routine prefix `name` carries, or None for a name that is not a routine address."""
    return next((prefix for prefix in PREFIXES if name.startswith(prefix)), None)


def is_routine(name, prefixes=PREFIXES):
    """Whether `name` is an `addrs.h` ROUTINE address of one of `prefixes`' components, by the naming rule."""
    return name.startswith(tuple(prefixes))


def core_symbol(name):
    """The C core an `addrs.h` routine name is reconstructed as: its name less the `ROM_`, lower-cased."""
    assert prefix_of(name), f"{name} is not a routine name of any component: {', '.join(p + '<X>' for p in PREFIXES)}"
    return name.replace(ROM_INFIX, "", 1).lower()


def role(name):
    """A routine's Tier 3 label: `Line-A linea_hline`, `VDI vsl_type`, `AES ob_offset`."""
    prefix = prefix_of(name)
    component, keeps_prefix = ROLE_OF_PREFIX[prefix]
    core = core_symbol(name)
    return f"{component} {core if keeps_prefix else core[len(prefix) - len(ROM_INFIX):]}"
