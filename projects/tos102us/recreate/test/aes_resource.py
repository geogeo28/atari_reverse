"""The RESOURCE layer's staging (`src/aes/resource.c`, `test_aes_resource*.py`): the snapshot's two relocated
resources, FRESH copies of them out of the ROM, a small application resource built by shape, and a model of get_addr.

THE SNAPSHOT'S RESOURCES are the ROM's own, copied into a TPA block at start-up and relocated there: the AES's (the
file selector, the alerts' strings; its global[] the one `AES_RS_SYSTEM_GLOBAL` names) and the desk's (its global[] at
`AES_DESK_APP_GLOBAL`, the one the desk's bindings hand in). The RAM copies are relocated; the ROM's bytes are the file
as it was — offsets from its header, coordinates in character cells — so a FRESH copy staged over the relocated one, at
the address the start-up relocated it at, is exactly what that relocation ran over: a routine's result can be held to
the captured machine's own bytes as well as to the ROM's run.

AN APPLICATION'S RESOURCE is input the AES takes from any program, and neither of the ROM's has an ICONBLK (both
headers count none): the icon arms are reached through one built here by shape (`application_resource`), every
section a real resource has, laid out as a resource file lays it out.
"""
import struct
import sys

from harness import BASE_IMAGE
from recreate_kit.os_map import OS_BUS_ADDR_MASK

import aes
import case
import staging
import vdi
from aes import LONG_ANSWER, WORD_ANSWER, signed
from case import merge_pokes

# `aes/resource.h`'s constants: the resource TYPES (R_*), RS_NO_ADDRESS, the ROM's resource bundle.
sys.modules[__name__].__dict__.update(aes.header_constants("resource.h"))

WORD_BYTES = aes.WORD_BYTES
LONG_BYTES = aes.LONG_BYTES

# ---- the two resources the snapshot holds, named -----------------------------------------------------------------
GEM_GLOBAL = case.long_in(BASE_IMAGE, aes.AES_RS_SYSTEM_GLOBAL)    # the AES's own global[]
DESK_GLOBAL = aes.AES_DESK_APP_GLOBAL                               # the desk's


def header_of(global_, image=BASE_IMAGE):
    """The resource header global[7..8] of the global[] at `global_` names."""
    return case.long_in(image, global_ + aes.AES_GLOBAL_PMEM)


GEM_HEADER = header_of(GEM_GLOBAL)
DESK_HEADER = header_of(DESK_GLOBAL)

# The header's words, by name — `aes/objects.h`'s RSH_* and the ones no routine reads by name.
HEADER_FIELDS = ("vrsn", "object", "tedinfo", "iconblk", "bitblk", "frstr", "string", "imdata", "frimg", "trindex",
                 "nobs", "ntree", "nted", "nib", "nbb", "nstring", "nimages", "rssize")


def header_words(header, image=BASE_IMAGE):
    """The resource header at `header` as `{field: word}`."""
    return dict(zip(HEADER_FIELDS, struct.unpack(f">{len(HEADER_FIELDS)}H", bytes(image[header:header + aes.RSH_BYTES]))))


# The two globals STALE, for a routine that sets them itself (rs_sglobal and its callers).
STALE_GLOBALS = aes.field_pokes("AES", RS_GLOBAL=0x00DE_AD00, RS_HDR=0x00BE_EF00)


def current(global_, header=None):
    """The resource globals set as rs_sglobal sets them: `global_` the caller's, its header the resource's."""
    header = header_of(global_) if header is None else header
    return aes.field_pokes("AES", RS_GLOBAL=global_, RS_HDR=header)


# ---- FRESH copies out of the ROM ----------------------------------------------------------------------------------
# The ROM keeps its resources as ONE bundle behind a table of five word offsets (`AES_RSC_BUNDLE`): the AES's
# resource starts after the table, the desk's at the first offset, each ending where the next starts.
BUNDLE = AES_RSC_BUNDLE
BUNDLE_OFFSET_COUNT = 5
BUNDLE_OFFSETS = struct.unpack(f">{BUNDLE_OFFSET_COUNT}H", bytes(BASE_IMAGE[BUNDLE:BUNDLE + BUNDLE_OFFSET_COUNT * WORD_BYTES]))
GEM_FRESH_AT = BUNDLE + BUNDLE_OFFSET_COUNT * WORD_BYTES
DESK_FRESH_AT = BUNDLE + BUNDLE_OFFSETS[0]


def rom_bytes(at, length):
    return bytes(BASE_IMAGE[at:at + length])


GEM_BYTES = header_words(GEM_FRESH_AT)["rssize"]
DESK_BYTES = header_words(DESK_FRESH_AT)["rssize"]
# ...and the LENGTH the start-up hands the relocation, out of the same table as it forms it ($fee50a, $fee542): the
# desk's the difference of the first two offsets; the AES's the first offset less the table's WORD count (`subq.w #5`)
# where the part starts past its BYTES — five bytes over, into the desk's.
GEM_PART_BYTES = BUNDLE_OFFSETS[0] - BUNDLE_OFFSET_COUNT
DESK_PART_BYTES = BUNDLE_OFFSETS[1] - BUNDLE_OFFSETS[0]
aes.declare_case_field(GEM_HEADER, GEM_BYTES, "the AES's resource, relocated at start-up: a fresh copy is staged over it")
aes.declare_case_field(DESK_HEADER, DESK_BYTES, "the desk's resource, the same way")


def fresh(global_):
    """The pokes that put the ROM's own, unrelocated copy of `global_`'s resource over the relocated one, at the
    address the start-up relocated it at — and that make it current."""
    header, source, length = ((GEM_HEADER, GEM_FRESH_AT, GEM_BYTES) if global_ == GEM_GLOBAL
                              else (DESK_HEADER, DESK_FRESH_AT, DESK_BYTES))
    return merge_pokes({header: rom_bytes(source, length)}, current(global_, header))


# ---- an APPLICATION's resource, built by shape --------------------------------------------------------------------
# In the free RAM above the stack band: a resource file of every section, and the global[] it is loaded for.
BAND_AT = 0xE0000
BAND_BYTES = 0x1000
staging.HIGH_BANDS.claim(BAND_AT, BAND_BYTES, "test/aes_resource.py: an application's resource and its global[]")
APP_GLOBAL = BAND_AT
GLOBAL_WORDS = 15                               # an application's global[]
GLOBAL_BYTES = 0x20                             # global[15], and a word over
APP_HEADER = BAND_AT + 0x40
# ...and past it, a caller's buffers: a command line and its tail, a path, a part of the ROM's resources.
BUFFER_BYTES = 0x100
PART_BUFFERS = 3                                   # the largest part a case copies is 534 bytes
BUFFER_AT = BAND_AT + BAND_BYTES - (2 + PART_BUFFERS) * BUFFER_BYTES
SECOND_BUFFER_AT = BUFFER_AT + BUFFER_BYTES
PART_AT = SECOND_BUFFER_AT + BUFFER_BYTES
PART_BYTES = PART_BUFFERS * BUFFER_BYTES


G_TEXT, G_STRING, G_ICON = 21, 28, 31     # the object types the built resource's blocks are named by
EXTENDED_TYPE = 0x1400                    # an application's own type number, in ob_type's high byte


def application_resource(header=APP_HEADER, *, icons=2, texts=2, bitblks=1, strings=3, images=1, trees=2, objects=7):
    """`(pokes, layout)`: a resource file at `header` as an application's would be BEFORE a load — every pointer an
    OFFSET from the header, every coordinate in cells — with `icons` ICONBLKs, `texts` TEDINFOs (each a text and a
    template of distinct lengths), `bitblks` BITBLKs, `strings` free strings, `images` free images and `trees` trees
    over `objects` objects. `layout` is `{section: offset}` and the counts, for the cases to name elements by."""
    blob = bytearray(aes.RSH_BYTES)
    layout = {}

    def place(section, data):
        layout[section] = len(blob)
        blob.extend(data)
        if len(blob) % 2:
            blob.append(0)
        return layout[section]

    text_bytes = [place(f"text{i}", b"TEXT" + b"x" * i + b"\0") for i in range(texts)]
    template_bytes = [place(f"tmplt{i}", b"__:__" + b"_" * (2 * i) + b"\0") for i in range(texts)]
    valid = place("valid", b"9999\0")
    string_bytes = [place(f"string{i}", b"STRING" + b"s" * i + b"\0") for i in range(strings)]
    image_data = place("imdata", bytes(range(32)))
    ted = place("tedinfo", b"".join(struct.pack(">III", text_bytes[i], template_bytes[i], valid) + bytes(aes.TE_BYTES - 12)
                                    for i in range(texts)))
    iconblk = place("iconblk", b"".join(struct.pack(">III", image_data, image_data + 16, string_bytes[0])
                                        + bytes(aes.IB_BYTES - 12) for _ in range(icons)))
    bitblk = place("bitblk", b"".join(struct.pack(">I", image_data) + bytes(aes.BI_BYTES - 4) for _ in range(bitblks)))
    frstr = place("frstr", b"".join(struct.pack(">I", string_bytes[i % len(string_bytes)]) for i in range(strings)))
    frimg = place("frimg", b"".join(struct.pack(">I", bitblk) for _ in range(images)))
    # Objects: the three types whose ob_spec is a colour (left alone) — one of them with an EXTENDED type in its high
    # byte, which the relocation masks off — between G_TEXT, G_ICON and G_STRING ones naming their blocks, and one
    # whose spec is -1, which the relocation leaves. Coordinates in cells, the high byte an offset.
    specs = [(aes.G_BOX, 0x00011100), (G_TEXT, ted), (EXTENDED_TYPE | aes.G_IBOX, 0x00FF1170), (G_ICON, iconblk),
             (aes.G_BOXCHAR, 0x41011181), (G_STRING, RS_NO_ADDRESS), (EXTENDED_TYPE | G_TEXT, ted + aes.TE_BYTES)]
    object_records = b"".join(
        struct.pack(">hhhHHHIHHHH", -1, -1, -1, specs[i % len(specs)][0], 0, 0, specs[i % len(specs)][1],
                    (i << 8) | 2, 1, 80 if i == 0 else 10 + i, 0x0103)
        for i in range(objects))
    obj = place("object", object_records)
    trindex = place("trindex", b"".join(struct.pack(">I", obj + t * aes.OB_BYTES) for t in range(trees)))
    words = dict(vrsn=0, object=obj, tedinfo=ted, iconblk=iconblk, bitblk=bitblk, frstr=frstr, string=string_bytes[0],
                 imdata=image_data, frimg=frimg, trindex=trindex, nobs=objects, ntree=trees, nted=texts, nib=icons,
                 nbb=bitblks, nstring=strings, nimages=images, rssize=len(blob))
    blob[:aes.RSH_BYTES] = struct.pack(f">{len(HEADER_FIELDS)}H", *(words[name] for name in HEADER_FIELDS))
    assert header + len(blob) <= BUFFER_AT
    layout.update(words)
    return {header: bytes(blob)}, layout


def application_global(header=APP_HEADER, global_=APP_GLOBAL):
    """The application's global[]: its header in global[7..8], every other word stale."""
    return merge_pokes({global_: bytes([vdi.FILL]) * GLOBAL_BYTES},
                       {global_ + aes.AES_GLOBAL_PMEM: struct.pack(">I", header)})


# ---- get_addr, as a model ------------------------------------------------------------------------------------------
SECTIONS = {R_OBJECT: "object", R_TEDINFO: "tedinfo", R_TEPTEXT: "tedinfo", R_ICONBLK: "iconblk", R_IBPMASK: "iconblk",
            R_BITBLK: "bitblk", R_BIPDATA: "bitblk"}
SIZES = {"object": aes.OB_BYTES, "tedinfo": aes.TE_BYTES, "iconblk": aes.IB_BYTES, "bitblk": aes.BI_BYTES}
FIELD_OF = {R_OBSPEC: (R_OBJECT, aes.OB_SPEC), R_TEPTMPLT: (R_TEDINFO, aes.TE_PTMPLT),
            R_TEPVALID: (R_TEDINFO, aes.TE_PVALID), R_IBPDATA: (R_ICONBLK, aes.IB_PDATA),
            R_IBPTEXT: (R_ICONBLK, aes.IB_PTEXT)}
# A free string's or image's table: the element's own address for R_FRSTR/R_FRIMG, the pointer it holds for
# R_STRING/R_IMAGEDATA.
TABLES = {R_FRSTR: ("frstr", False), R_STRING: ("frstr", True), R_FRIMG: ("frimg", False), R_IMAGEDATA: ("frimg", True)}


def model_get_addr(image, aes_type, index):
    """What get_addr answers for `aes_type`/`index` over the resource globals in `image`."""
    header = case.long_in(image, aes.AES_RS_HDR)
    section_index = {name: i for i, name in enumerate(HEADER_FIELDS)}

    def sub(section, size):
        offset = case.word_in(image, (header + 2 * section_index[section]) & OS_BUS_ADDR_MASK)
        return (header + offset + signed(size) * signed(index)) & 0xFFFFFFFF

    def long_at(address):
        return case.long_in(image, address & OS_BUS_ADDR_MASK)

    aes_type &= 0xFFFF
    if aes_type == R_TREE:
        table = long_at(case.long_in(image, aes.AES_RS_GLOBAL) + aes.AES_GLOBAL_PTREE)
        return long_at(table + signed(index * LONG_BYTES))
    if aes_type in SECTIONS:
        return sub(SECTIONS[aes_type], SIZES[SECTIONS[aes_type]])
    if aes_type in FIELD_OF:
        block_type, field = FIELD_OF[aes_type]
        return (model_get_addr(image, block_type, index) + field) & 0xFFFFFFFF
    if aes_type in TABLES:
        section, dereferenced = TABLES[aes_type]
        entry = sub(section, LONG_BYTES)
        return long_at(entry) if dereferenced else entry
    return RS_NO_ADDRESS


# ---- the signatures (`vdi.declare_alcyon`: the Tier 3 call and the shipped glue read them) --------------------------
FIX_CHPOS = "AES_ROM_FIX_CHPOS"
RS_OBFIX = "AES_ROM_RS_OBFIX"
GET_SUB = "AES_ROM_GET_SUB"
GET_ADDR = "AES_ROM_GET_ADDR"
FIX_TRINDEX = "AES_ROM_FIX_TRINDEX"
FIX_OBJECTS = "AES_ROM_FIX_OBJECTS"
FIX_TEDINFO = "AES_ROM_FIX_TEDINFO"
DO_RSFIX = "AES_ROM_DO_RSFIX"
FIX_NPTRS = "AES_ROM_FIX_NPTRS"
FIX_PTR = "AES_ROM_FIX_PTR"
FIX_LONG = "AES_ROM_FIX_LONG"
RS_SGLOBAL = "AES_ROM_RS_SGLOBAL"
RS_GADDR = "AES_ROM_RS_GADDR"
RS_SADDR = "AES_ROM_RS_SADDR"
RS_FIXIT = "AES_ROM_RS_FIXIT"
IMAGE, WORD, LONG = vdi.IMAGE_ARG, vdi.WORD_ARG, vdi.LONG_ARG
SIGNATURES = {
    FIX_CHPOS: (None, (IMAGE, LONG, WORD)),
    RS_OBFIX: (WORD_ANSWER, (IMAGE, LONG, WORD)),
    GET_SUB: (LONG_ANSWER, (IMAGE, WORD, WORD, WORD)),
    GET_ADDR: (LONG_ANSWER, (IMAGE, WORD, WORD)),
    FIX_TRINDEX: (None, (IMAGE,)),
    FIX_OBJECTS: (WORD_ANSWER, (IMAGE,)),
    FIX_TEDINFO: (None, (IMAGE,)),
    DO_RSFIX: (None, (IMAGE, LONG, WORD)),
    FIX_NPTRS: (None, (IMAGE, WORD, WORD)),
    FIX_PTR: (WORD_ANSWER, (IMAGE, WORD, WORD)),
    FIX_LONG: (WORD_ANSWER, (IMAGE, LONG)),
    RS_SGLOBAL: (None, (IMAGE, LONG)),
    RS_GADDR: (WORD_ANSWER, (IMAGE, LONG, WORD, WORD, LONG)),
    RS_SADDR: (WORD_ANSWER, (IMAGE, LONG, WORD, WORD, LONG)),
    RS_FIXIT: (WORD_ANSWER, (IMAGE, LONG)),
}
for _name, (_restype, _argtypes) in SIGNATURES.items():
    aes.declare_alcyon(_name, _restype, _argtypes)


def run(name, arguments, pokes=None, **kwargs):
    """`name` over the leaf machine and `pokes`."""
    return aes.run_function(name, arguments, aes.leaf_machine(onto=pokes), **kwargs)
