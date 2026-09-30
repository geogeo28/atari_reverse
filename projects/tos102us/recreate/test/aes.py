"""THE AES STAGING DOOR — how every AES battery stages a call and reads it back (`test/vdi.py`'s shape, one component over).

HOW AN AES ROUTINE IS ENTERED. GEM never enters one through its own ABI: `trap #2` reaches the dispatcher, whose arm
calls the implementation by LINE-F — a `$F000|off` word, whose exception handler (vector $2c, a RAM copy at
`AES_LINEF_COPY`) jumps through the ROM call table — and every Alcyon routine returns by a `$F001|m` word, whose handler
restores the registers `m` names. The C reconstruction calls by `jsr` and returns by `rts`: the SAME machine but for one
word, `AES_LINEF_MASK_WORD`, which the handler rewrites with the mask of every non-empty masked return and C never
writes. So an AES case is run two ways, over the same frame:

  * DIRECT (`run_function`): entered by `jsr` at the routine, as a VDI helper is — the row Tier 3 prices;
  * THROUGH LINE-F (`run_function(..., through_line_f=True)`): entered at a staged caller that makes the ROM's own
    call word (`line_f_caller_pokes`), so the handler's call path runs too — verified, and unpriced, as `vdi`'s rows entered
    through the Line-A exception are (the entry is the stub, not the routine).

Both drop the mask word by name (`LINE_F_MASK_WINDOW`, a `case.run` `dropped_windows` entry: only if the ROM's run stores
it). A priced row whose ROM run stores it drops it at Tier 3 too (`register`: `dropped=` with the `undropped=` companion
the rule requires — the same machine, the word staged at the value the run leaves, compared without the pass).

WHAT THE SNAPSHOT MUST NOT BE TRUSTED FOR. It is taken inside the dispatcher's idle loop (`aes/aes.h`): `AES_RLR` is
NULL, so a routine reading `rlr->…` would read the vector page — `leaf_machine()` stages a running PD, over the
dispatcher's guard (`AES_INDISP`, whose 1 makes `dsptch` a bare `rts`: a lever, not the machine's behaviour). The
AES's VDI contrl[] is in the capture MASK; a case reaching the VDI stages its own.

---- WHAT THE HEADERS DO NOT NAME, AND WHY ------------------------------------------------------------------------
`include/aes/*.h` carries only fields a ROM instruction was found reading or writing. Left out, until a reconstructed
routine reads them by name: PD +32/+38 (p_evbits, p_evlist: the map's reading, uncited), EVB +24 (e_return), the CDA's
other words, WINDOW +8..+15 and +52.., TEDINFO +12..+22, ICONBLK +12..+32, BITBLK +4..+12, and RSHDR +0/+12/+14/+28..+34
(version, strings, image data, and the counts rsrc_load reads only through the header copy's length).
"""
import functools
import struct
import sys
from collections import namedtuple
from pathlib import Path

from harness import BASE_IMAGE, _lib, addrs, emu, make_image

import case
import layouts
import routines
import staging
import vdi
from case import merge_pokes
from opcodes import DROP_STACK_LONG, LINE_F, PUSH_ADDRESS_SHORT, RTS

# ---- the headers' constants, and the FIELDS (`test/layouts.py`, the one reader of the width tags) ------------------
_INCLUDE = Path(__file__).resolve().parents[1] / "include"
# `aes/aes.h` is included by no C yet — nothing reconstructed reads the AES's RAM by name — so its constants and widths
# reach the host through this parse alone; the first core that reads one includes it, and the compiler checks it then.
AES_HEADERS = tuple(_INCLUDE / name for name in ("aes/aes.h", "aes/objects.h"))
CONSTANTS = layouts.parse_constants(AES_HEADERS)
sys.modules[__name__].__dict__.update(CONSTANTS)

WORD_BYTES = layouts.WORD_BYTES
LONG_BYTES = layouts.LONG_BYTES
STALE_WORD = vdi.STALE_WORD

# A record is a constant-name prefix: AES (absolute addresses in GEMBSS), and every record's offsets.
RECORDS = ("AES", "PD", "UDA", "CDA", "EVB", "FORK", "WIN", "OB", "TE", "IB", "BI", "UB", "GRECT", "ORECT", "RSH")
RECORD_BYTES = {"PD": PD_BYTES, "UDA": UDA_STATE_BYTES, "CDA": CDA_BYTES, "EVB": EVB_BYTES, "FORK": FORK_ENTRY_BYTES,
                "WIN": WIN_BYTES, "OB": OB_BYTES, "TE": TE_BYTES, "IB": IB_BYTES, "BI": BI_BYTES, "UB": UB_BYTES,
                "GRECT": GRECT_BYTES, "ORECT": ORECT_BYTES, "RSH": RSH_BYTES}

# ---- the window, and the bands in it --------------------------------------------------------------------------------
# Above the VDI's window and below the stack guard, dead in the snapshot (`test_aes_door.py` holds both).
WINDOW_AT = 0x78000
WINDOW_BYTES = 0x2000
SPAN = staging.Registry(WINDOW_AT, WINDOW_AT + WINDOW_BYTES, "the AES's staged window")
LAYOUTS = layouts.Layouts(AES_HEADERS, RECORDS, CONSTANTS, require=SPAN.require_claimed, where="`aes/aes.h`, THE WIDTH TAG")
FIELDS = LAYOUTS.fields

# A TOP BYTE on a pointer argument: the 68000's bus drops it, and an application's tree or answer pointer reaches
# the AES through addrin unmasked, so a battery hands one in to hold every pointer's `bus_dereference`.
BUS_TAG = 0x5A000000

TREE_OBJECTS = 40                       # the widest tree a case stages: the snapshot's own run to 25
TREE_BYTES = TREE_OBJECTS * OB_BYTES
BLOCKS_BYTES = 0x200                    # TEDINFOs, ICONBLKs, USERBLKs and the strings they point at
RECTS_BYTES = 0x100                     # GRECTs, and the words a routine answers through
LINE_F_CALLER_SLOT_BYTES = 0x10         # THE staged Line-F caller (`line_f_caller_pokes`): a case enters one routine
TREE_AT = SPAN.claim(WINDOW_AT, TREE_BYTES, "a staged object tree")
BLOCKS_AT = SPAN.claim(TREE_AT + TREE_BYTES, BLOCKS_BYTES, "the blocks a staged tree's ob_spec points at")
RECTS_AT = SPAN.claim(BLOCKS_AT + BLOCKS_BYTES, RECTS_BYTES, "staged GRECTs and answer words")
LINE_F_CALLER_AT = SPAN.claim(RECTS_AT + RECTS_BYTES, LINE_F_CALLER_SLOT_BYTES, "the Line-F caller")


def field(record, name):
    """`record`'s field `name` — a KeyError naming it when the headers have no FIELD of that name."""
    return LAYOUTS.field(record, name)


def field_pokes(record, base=0, **values):
    """Fields of `record` at `base`, by name — `field_pokes("OB", at, X=16)`. AES's fields are absolute: base 0."""
    return LAYOUTS.pokes(record, base, **values)


def read_field(image, record, name, base=0):
    """A field back out of `image`: an int, or a list of elements for an array."""
    return LAYOUTS.read(image, record, name, base)


# ---- (a) the MACHINE: the snapshot's scheduler state, and the running process a case stages ------------------------
# What the capture holds, named so a case says which part of it it relies on (`test_aes_door.py` pins each).
SHELL_PD = AES_PD_TABLE                         # PD0: the shell and the desk, blocked in evnt_multi
SCREEN_MANAGER_PD = AES_PD_TABLE + PD_BYTES     # PD1: SCRENMGR, the control manager, blocked too
SNAPSHOT_RLR = 0                                # nothing running: the CPU is in disp's idle loop
SNAPSHOT_NOT_READY = (SHELL_PD, SCREEN_MANAGER_PD)
SNAPSHOT_MASK_WORD = case.word_in(BASE_IMAGE, AES_LINEF_MASK_WORD)     # the last masked return before the capture


def leaf_machine(onto=None):
    """The AES as a routine that never reaches `dsptch` runs in it, over `onto`: the shell's PD RUNNING (`AES_RLR`,
    NULL in the snapshot) and the dispatcher's guard `AES_INDISP` at the snapshot's own 1 — a lever that makes
    `dsptch` a bare `rts`, inert for such a routine. A routine that DOES reach `dsptch` needs the running process and
    the guard as its own case's choices (a clear guard really enters disp), which no battery stages yet."""
    return merge_pokes(onto, field_pokes("AES", RLR=SHELL_PD, INDISP=AES_INDISP_SET))


def list_of(image, head):
    """The PDs a scheduler list at `head` (AES_RLR, AES_NRL, AES_DRL) links, in order."""
    pds, at = [], case.long_in(image, head)
    while at:
        pds.append(at)
        assert len(pds) <= AES_PD_COUNT, f"the list at {head:#x} does not end"
        at = case.long_in(image, at + PD_LINK)
    return pds


# ---- (b) OBJECT TREES: staged by SHAPE, and the snapshot's own ------------------------------------------------------
Object = namedtuple("Object", "parent fields")


def node(parent, **fields):
    """One object of a staged tree: its PARENT's index (None for the root) and any OB_* fields by name."""
    return Object(parent, fields)


def links(objects):
    """`[(next, head, tail)]` for `objects` (`node`s, children in index order), as ob_add links a tree: a parent's
    head its first child and tail its last, a child's next its next sibling — the LAST child's next its PARENT —
    the root's next and every leaf's head/tail OB_NIL."""
    linked = [[OB_NIL, OB_NIL, OB_NIL] for _ in objects]
    for index, obj in enumerate(objects):
        if obj.parent is None:
            assert index == OB_ROOT, "the root is object 0, and the only one without a parent"
            continue
        parent = linked[obj.parent]
        if parent[1] == OB_NIL:
            parent[1] = index
        else:
            linked[parent[2]][0] = index
        parent[2] = index
        linked[index][0] = obj.parent
    return [tuple(entry) for entry in linked]


def object_pokes(tree, index, **fields):
    """Fields of object `index` of the tree at `tree`, by name."""
    return field_pokes("OB", tree + index * OB_BYTES, **fields)


def tree_pokes(objects, at=TREE_AT):
    """A tree of `objects` (`node`s) at `at`, linked by `links` — every field not named zero, so a case says only
    what it relies on and the links are the builder's, not typed."""
    assert len(objects) <= TREE_OBJECTS or at != TREE_AT, "more objects than the tree band holds"
    pokes = {at: bytes(len(objects) * OB_BYTES)}
    for index, (obj, (following, head, tail)) in enumerate(zip(objects, links(objects))):
        pokes = merge_pokes(pokes, object_pokes(at, index, NEXT=following, HEAD=head, TAIL=tail, **obj.fields))
    return pokes


def tedinfo_pokes(at, **fields):
    return field_pokes("TE", at, **fields)


def iconblk_pokes(at, **fields):
    return field_pokes("IB", at, **fields)


def userblk_pokes(at, **fields):
    return field_pokes("UB", at, **fields)


def grect_pokes(at, x, y, w, h):
    """A GRECT at `at`: four words, each a signed or unsigned 16-bit value."""
    return field_pokes("GRECT", at, X=x, Y=y, W=w, H=h)


def read_object(image, tree, index):
    """Object `index` of the tree at `tree` in `image`, as `{field: value}` (unsigned words, the spec a long)."""
    return {name: read_field(image, "OB", name, tree + index * OB_BYTES) for name in FIELDS["OB"]}


# THE TREE AS ITS LINKS SAY — the model the batteries hold a walk to. The AES walks by links alone; the model needs
# the tree's length to know which objects are candidates, which the resource format marks with OB_FLAG_LASTOB.
def tree_length(tree, image=BASE_IMAGE):
    """How many objects the tree at `tree` has: up to the one flagged OB_FLAG_LASTOB."""
    for index in range(TREE_OBJECTS):
        if read_field(image, "OB", "FLAGS", tree + index * OB_BYTES) & OB_FLAG_LASTOB:
            return index + 1
    raise AssertionError(f"the tree at {tree:#x} has no LASTOB object in its first {TREE_OBJECTS}")


def parent_of(tree, index, image=BASE_IMAGE):
    """The parent as the tree's links say: the object whose head..tail run of children holds `index`."""
    for candidate in range(tree_length(tree, image)):
        head = vdi.signed_word(read_field(image, "OB", "HEAD", tree + candidate * OB_BYTES))
        child = head
        while head != OB_NIL and child != candidate:
            if child == index:
                return candidate
            child = vdi.signed_word(read_field(image, "OB", "NEXT", tree + child * OB_BYTES))
    return OB_NIL


# THE SNAPSHOT'S OWN TREES: the AES's ROM resource, relocated into GEMBSS at start-up and reached as rsrc_gaddr reaches
# it — AES_RS_SYSTEM_GLOBAL's global[], its header (global[7..8]), the header's tree table. Real data a case seeds from.
def resource_header(image=BASE_IMAGE):
    return case.long_in(image, case.long_in(image, AES_RS_SYSTEM_GLOBAL) + AES_GLOBAL_PMEM)


def resource_tree(index, image=BASE_IMAGE):
    """The address of tree `index` of the AES's own resource, as the captured machine has it."""
    header = resource_header(image)
    assert 0 <= index < case.word_in(image, header + RSH_NTREE)
    return case.long_in(image, header + case.word_in(image, header + RSH_TRINDEX) + index * LONG_BYTES)


# ---- (c) LINE-F: the handler's patched word, and a caller that makes the ROM's own call ----------------------------
LINE_F_MASK_WHY = ("the Line-F handler's own `movem` mask, rewritten by every masked Alcyon return (`aes/aes.h`); "
                   "the C returns by `rts` and never writes it")
LINE_F_MASK_WINDOW = ((AES_LINEF_MASK_WORD, AES_LINEF_MASK_WORD + WORD_BYTES, LINE_F_MASK_WHY),)


def line_f_target(word):
    """The routine a Line-F CALL word names through the ROM's call table — None for any other word (a return, or
    not a Line-F word at all)."""
    if word & ~LINEF_OFFSET_MASK != LINE_F or word & LINEF_RETURN_BIT:
        return None
    return case.long_in(BASE_IMAGE, AES_LINEF_TABLE + (word & LINEF_OFFSET_MASK))


@functools.cache
def line_f_call_sites(name):
    """`{call word: (address, ...)}`: every even word of the GEM text that Line-F-calls `addrs.<name>`, by word."""
    routine, sites = getattr(addrs, name), {}
    for at in range(addrs.AES_ROM_GEM_ENTRY, AES_LINEF_TABLE, WORD_BYTES):
        word = case.word_in(BASE_IMAGE, at)
        if line_f_target(word) == routine:
            sites[word] = (*sites.get(word, ()), at)
    return sites


def line_f_call_word(name):
    """The `$F000|off` word a case calls `addrs.<name>` by. The table names some routines twice (ob_offset at $154
    and $208), and either word reaches the same code: a case enters through the word MOST of the ROM's callers use,
    the lowest on a tie."""
    sites = line_f_call_sites(name)
    assert sites, f"{name} (${getattr(addrs, name):x}) is called by no Line-F word in the GEM text"
    return max(sorted(sites), key=lambda word: len(sites[word]))


# THE CALLER: `addq.l #4,sp` (the sentinel's slot becomes the callee's return slot, so the frame at abi.FIRST_ARG is
# where the callee's `link` finds it), the call word, and the run's own return — which the call overwrote — pushed
# back for the `rts`. The two stack writes are the stack band's, which no diff compares. ONE place for every routine
# (a case enters one), so a row's entry does not depend on which routine some other battery staged first; the call
# word, which is the routine's, is in the row's pokes. `pea (SENTINEL).w` sign-extends: harmless while SENTINEL is
# below $8000, which `test_aes_door` holds.
LINE_F_CALLER_BYTES = len(DROP_STACK_LONG) + WORD_BYTES + len(PUSH_ADDRESS_SHORT) + WORD_BYTES + len(RTS)
assert LINE_F_CALLER_BYTES <= LINE_F_CALLER_SLOT_BYTES


def line_f_caller_pokes(name):
    """The bytes of the Line-F caller of `addrs.<name>`, at its place."""
    stub = (DROP_STACK_LONG + struct.pack(">H", line_f_call_word(name))
            + PUSH_ADDRESS_SHORT + struct.pack(">H", emu.SENTINEL) + RTS)
    return {LINE_F_CALLER_AT: stub}


# ---- (c') ROM CODE ADDRESSES AS VALUES, owed by the C ports of forkq's callers, forker and ap_trecd -----------------
# The fork queue in THEGLO (compared) holds ROM code addresses: every forkq caller queues a fork function by its ROM
# address, an IMMEDIATE — pushed straight onto the call's frame, or (ap_tplay) stored in the local its one forkq call
# pushes — and forker later `jsr`s through it; forker's recorder and ap_trecd then COMPARE a queued entry against
# three of them. A host C port must store and compare the ROM's values; a rebuilt ROM, the address its own fork
# function is linked at: the CODE kind of `test_vdi_rom_data.py`'s census, listed here until those routines have a
# source file to be listed under (`test_aes_door` holds that these are every longword of the GEM text naming a fork
# function, and that every forkq call queues one). The OPPOSITE policy holds for the Line-F handler's 100-byte RAM
# copy: it carries `movea.l #$fee900,a0` and the head of the call table as ORIGINAL ROM addresses, kept at the
# original's value and never relocated (so on a rebuilt ROM a Line-F executed jumps through $fee900 into unrelated
# bytes).
TCHANGE, KCHANGE, BUTTON_CHANGE, MCHANGE = (addrs.AES_ROM_TCHANGE, addrs.AES_ROM_KCHANGE, addrs.AES_ROM_BCHANGE,
                                           addrs.AES_ROM_MCHANGE)
FORK_FUNCTION_IMMEDIATES = (    # (the instruction whose immediate names it, the fork function)
    (0xFE4C2A, KCHANGE),        # forker's recorder: `cmp.l #`, three
    (0xFE4C54, TCHANGE),
    (0xFE4C6C, TCHANGE),
    (0xFE4D5C, KCHANGE),        # chkkbd: `move.l #,-(sp)` onto forkq's frame
    (0xFE4F9E, BUTTON_CHANGE),  # b_click, pushed
    (0xFE4FDA, BUTTON_CHANGE),  # b_delay, pushed twice
    (0xFE4FFC, BUTTON_CHANGE),
    (0xFE66D2, MCHANGE),        # ap_tplay: a recorded event's fcode, into the local its forkq call pushes
    (0xFE66E4, BUTTON_CHANGE),
    (0xFE66EE, KCHANGE),
    (0xFE67D6, TCHANGE),        # ap_trecd: an entry's function back to its fcode, `cmp.l #`, four
    (0xFE67E4, MCHANGE),
    (0xFE67F2, KCHANGE),
    (0xFE6800, BUTTON_CHANGE),
    (0xFED3F8, MCHANGE),        # the mouse-motion interrupt glue, pushed
    (0xFED44E, TCHANGE),        # the timer interrupt glue, pushed
)
FORKQ_CALL_OF_A_LOCAL = addrs.AES_AP_TPLAY_FORKQ_CALL


# ---- (d) the run doors: an ALCYON AES routine, over the frame its caller pushed -----------------------------------
# The signature registry is `vdi.declare_alcyon` — ONE for every Alcyon core, which `bench/tier3.py` derives the Tier 3
# call from and `bench/shipped_glue.py` repacks a GCC call by. `routines.core_symbol` names the core (`aes_<x>`).
declare_alcyon = vdi.declare_alcyon
alcyon_frame = vdi.alcyon_frame
WORD_RESULT = vdi.WORD_RESULT


class Result(case.Result):
    """A run and the machine after it (`case.Result`), read as the AES's records."""

    def object(self, tree, index):
        return read_object(self.final, tree, index)

    def field(self, record, name, base=0):
        return read_field(self.final, record, name, base)

    def answer(self):
        """The word in D0, as the signed Alcyon `int` a caller reads."""
        return vdi.signed_word(self.info["regs"]["d0"] & 0xFFFF)


def entry_of(name, through_line_f):
    """Where a case of `addrs.<name>` is entered: the routine, or its Line-F caller."""
    return LINE_F_CALLER_AT if through_line_f else getattr(addrs, name)


def staged(name, arguments, pokes, *, through_line_f=False):
    """`pokes` with `name`'s frame of `arguments` at abi.FIRST_ARG, and its Line-F caller when it is entered by one."""
    frame = alcyon_frame(name, *arguments)
    return merge_pokes(pokes, frame, line_f_caller_pokes(name) if through_line_f else None)


# THE ATTRIBUTION PASS RUNS on every AES case (`case.run`'s default). The mask word is a `dropped_windows` entry, which
# the kit leaves out of the plain compare BEFORE it decides to run the pass and then neither poisons nor compares
# (`harness.differential`'s `dropped`) — so every other byte a case's ROM run stores keeps skipped-store detection.
# The one exception is the Tier 3 COMPANION (`undropped`, below).


def run_function(name, arguments, pokes, *, through_line_f=False, dropped_windows=LINE_F_MASK_WINDOW, **kwargs):
    """The Alcyon AES routine `addrs.<name>` over the frame of `arguments`, against its core called with the same
    values, the answer compared at the signature's width and `dropped_windows` — the mask word, by default — dropped where
    the ROM's run stores it. `kwargs` are `case.run`'s. Answers a `Result`."""
    signature = vdi.ALCYON[name]
    core = getattr(_lib, routines.core_symbol(name))
    arguments = vdi.as_signed(name, arguments)
    machine_pokes = staged(name, arguments, pokes, through_line_f=through_line_f)
    info = case.run(entry_of(name, through_line_f), {"_pokes": machine_pokes}, lambda _lib_, buf: core(buf, *arguments),
                    width=WORD_RESULT if signature.restype is not None else case.NO_RESULT,
                    dropped_windows=dropped_windows, **kwargs)
    return Result(info, machine_pokes)


def settled_mask_word(name, arguments, pokes):
    """The mask word the ROM's own run of `name` over `pokes` leaves — or None when it never stores it (a routine
    that returns by `rts` and calls none that return by a mask)."""
    image = make_image(staged(name, vdi.as_signed(name, arguments), pokes))
    _final, writes, _regs = emu.run(image, getattr(addrs, name))
    if AES_LINEF_MASK_WORD not in writes:
        return None
    return writes[AES_LINEF_MASK_WORD] << 8 | writes[AES_LINEF_MASK_WORD + 1]


# The companion runs WITHOUT the attribution pass: with nothing dropped, the pass would invert the mask word, which
# the ROM's run rewrites and the C never writes — a canary no reconstruction can clear. What it is for survives: a C
# that WRITES the mask word differs from the staged value on the plain compare, which a drop would hide.
COMPANION_UNPOISONED = {"poison": False}


def undropped(name, arguments, pokes):
    """A priced row's Tier 3 COMPANION: the SAME machine — the mask word staged at the value the run leaves, which the
    ROM's run then rewrites with itself — as a differential with NOTHING dropped."""
    return run_function(name, arguments, pokes, dropped_windows=(), **COMPANION_UNPOISONED)


# ---- (e) the registry --------------------------------------------------------------------------------------------
# `test_boot_snapshot.VERIFIED_CASES` splats `CASES`; `UNPRICED` holds the rows entered through a Line-F caller.
ROWS = case.Rows("the AES")
CASES = ROWS.cases
UNPRICED = ROWS.unpriced


def register(label, name, arguments, pokes, *, through_line_f=False):
    """One `VERIFIED_CASES` row of `name` over the frame of `arguments`, named `<core>, <label>`. A DIRECT row is
    priced; if the ROM's run stores the mask word, the row stages it at the value the run leaves and drops it at
    Tier 3, with its companion. A row THROUGH LINE-F is verified and unpriced."""
    row_name = f"{routines.core_symbol(name)}, {label}"
    if through_line_f:
        return ROWS.register(row_name, LINE_F_CALLER_AT, staged(name, arguments, pokes, through_line_f=True),
                             priced=False)
    settled = settled_mask_word(name, arguments, pokes)
    if settled is None:
        return ROWS.register(row_name, getattr(addrs, name), staged(name, arguments, pokes))
    pokes = merge_pokes(pokes, field_pokes("AES", LINEF_MASK_WORD=settled))
    return ROWS.register(row_name, getattr(addrs, name), staged(name, arguments, pokes), dropped=LINE_F_MASK_WINDOW,
                         undropped=functools.partial(undropped, name, arguments, pokes))


# ---- (f) what the snapshot mask is checked against ------------------------------------------------------------------
_CASE_FIELDS = [
    (AES_RLR, LONG_BYTES, "the running PD a case stages"),
    (AES_INDISP, 1, "the dispatcher's guard a case decides"),
    (AES_LINEF_MASK_WORD, WORD_BYTES, "the Line-F handler's mask word a priced row stages"),
]


def declare_case_field(at, size, why):
    """A span a battery's cases reach OUTSIDE the window and the fields above — the one door for it."""
    _CASE_FIELDS.append((at, size, why))


def case_fields():
    """Every span an AES case reads or pokes: the fields above, every battery's `declare_case_field`, and every band
    of the window AS CLAIMED WHEN ASKED."""
    return (*_CASE_FIELDS, *SPAN.claims)
