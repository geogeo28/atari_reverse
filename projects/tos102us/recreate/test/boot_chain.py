r"""THE CHAINED BOOT (boot CH, `test_boot_chain.py`): OUR boot run from the reset to `$fc047a` and on to `gem_entry` — every
slice of ours in sequence, the ROM's own code everywhere we have not ported — against THE ROM'S OWN BOOT from the same
machine, on WARM and COLD and four of B5's arms, the blank disk in drive A:.

THE USER'S RULINGS IT STANDS ON (2026-11-01): R-CH-1 "Steered chain" — each slice on ITS OWN EXISTING STAGING, the machine
CARRIED WHOLE between slices, the harness checking the arrival at the ROM's next slice start and steering the PC into ours:
A CHAINED STAGING (`CHAINED_LABEL`); with it a STATIC LINK CHECK (`exits`, `link_check`): EVERY `jmp.l` INTO THE ROM
WINDOW each product holds (the blob's: in B2's and B3's entries), PINNED EXACTLY as a multiset — the slice-start ones
the steering's map, the rest (the display's to the sync wait) named. D10 DEFERRED: no composed image
(the head's laid span `$fc6000` lies over GEMDOS code the launch runs — STATUS's first item owed if D10 is taken up).
The BLANK DISK only: B4's one-program arm is not chained (its Pexec(0) clears the TPA, which holds the bench blob and so
the targets of our linked vectors). Every earlier ruling each slice stands on stands here with it: D3, D4, D5, D7, D8,
D9, "ROM-window overlay", "Own link rule", R-B4-2, R-B4-3, R-B5-1.

THE STEPS (`STEPS`), each the slice's own staging and declarations, the next started from the machine the last left:
  head  [$fc0030, $fc02cc)   the head's overlay, entered at our reset (`boot_head.ours_of`); ours stops at its own end
  B2    [$fc02cc, $fc03b6)   THE BENCH BLOB LAID HERE on both shores (B2's staging, at its own start: the cold arm's clear
                             of `$400..phystop` lies behind) — on the ROM's shore too, held equal without it outside its span
  B3    [$fc03b6, $fc03e0)   its two legs (the 6850's shared address, B3's interim call), B3's declarations
  B5    [$fc03e0, $fc0452)   the arm's declarations; the mono arm's poll answered (R-B5-1)
  B6    [$fc0452, $fc047a)   the four waits answered, the three observed entries watched for the ledger and not for the price
  B4    [$fc047a, gem_entry) the launch on the blank disk through `boot_launch.run` (the floppy model, the clock answered)
At each boundary OUR run must arrive at the ROM's next slice start (the head: at its own end, the ROM's by offset) and
is ENTERED at our next product's entry (`steering`) — read off the products (`link_check`), never typed twice.

WHAT IS HELD at each boundary (`differences`): the stop; EVERY register but the carries a slice names, EXACTLY the set
measured (`CARRIED`: B2's scratch and its A3/A4, B3's — every one of them dead by `$fc0452`, the composition proving
what each slice could only argue), the head's links by offset while they live; THE MEGABYTE with only the named
mappings — the linked vectors (B2's and B3's `LINKED`), at gem_entry the launch's links (`boot_launch.linked`) and the
RETURN ADDRESSES INTO OUR CODE that GEMDOS's and the AUTO runner's dead frames keep INSIDE the pre-init mask
(`our_returns`) — outside each boundary's derived stack residue (B2's, B3's, B6's dead classes; the BIOS stack's
dead frames TIGHTENED for the chain: `FRAMES_APART_FROM`, and at gem_entry the exact `APART_AT_THE_END`); every ordered ledger of
every step; B6's answers; B4's GEMDOS, floppy, clock and blank ledgers. THE END SURFACES (COLD): at `$fc047a` the mid-boot
capture apart in exactly B6's D1 class (D4's gone: B6 runs the floppy through the FDC model); at gem_entry the
pre-init capture apart in its own exact set (`END_PREINIT`).

THE HAND-OFF NO SLICE SEES: B2 and B3 store our linked entries in the vectors, and the ROM's own code after them enters
them — the BIOS/XBIOS traps GEMDOS makes, the horizontal blanks the launch takes. Counted (`trap_calls`, `Step.spent`), on ours in our
`trap.S` and `isr_hbl_entry`, on the ROM's in its dispatcher and its HBL handler: so a vector left the ROM's is red. Every step of ours is vetted
against THE UNION of the spans the boot ports (`PORTED_UNION`, `_vet_who_ran`).

ITS PRICE (ruling D9, `priced`): each shore's OWN cycles — ours every cycle in our products and in the blob (our linked
`trap.S` and ISR entries among them); the ROM's in each step's ported spans and in its own dispatcher and HBL handler —
and THE REST, each step's every other cycle, held equal step by step.
"""
import functools
import struct
from collections import namedtuple

from harness import addrs, emu

import midboot_snapshot
import preinit_snapshot

import boot
import boot_display
import boot_head
import boot_hwinit
import boot_late
import boot_launch
import boot_sysvars

WORD_BYTES, LONG_BYTES = boot.WORD_BYTES, boot.LONG_BYTES
JMP_ABSOLUTE_LONG = boot_display.JMP_ABSOLUTE_LONG
LEA_ABSOLUTE_LONG_BYTES, LEA_PC_RELATIVE_BYTES = 6, 4
LEA_ABSOLUTE_LONG_CYCLES, LEA_PC_RELATIVE_CYCLES = 12, 8   # `lea abs.l,a0` / `lea d16(pc),a0`: trap.S's +4 a call
JSR_INDIRECT_A0 = 0x4e90                # the dispatchers' `jsr (a0)`: its return is what GEMDOS's frames keep
CHAINED_LABEL = ("CHAINED STAGING (ruling R-CH-1 \"Steered chain\"): each slice on its own staging, the machine carried "
                 "whole between them, the PC steered at each boundary from the ROM's next slice start into ours")
DISK = boot_launch.BLANK

# ---- THE CHAINS: a machine and B5's arm (the capture's — colour, ST low, no blitter — and three more) -----------------
Chain = namedtuple("Chain", "machine arm")
CAPTURE_ARM = {machine: boot_late.DISPLAY_ARM[machine] for machine in boot_late.MACHINES}
OTHER_ARMS = ((addrs.SHIFTER_MODE_LOW, boot_display.MONO, boot_display.ABSENT),
              (addrs.SHIFTER_MODE_LOW, boot_display.COLOUR, boot_display.PRESENT),
              (addrs.SHIFTER_MODE_MEDIUM, boot_display.COLOUR, boot_display.ABSENT))
SLICES = {
    **{f"boot chain, {machine}": Chain(machine, CAPTURE_ARM[machine]) for machine in boot_late.MACHINES},
    **{f"boot chain, {machine}, {boot_display.name_of(arm).split(f'{machine}, ', 1)[1]}": Chain(machine, arm)
       for machine in boot_late.MACHINES
       for arm in (boot_display.Arm(machine, *other) for other in OTHER_ARMS)},
}

# ---- THE BOUNDARIES, AND THE STEERING READ OFF THE PRODUCTS -------------------------------------------------------------
HEAD, B2, B3, B5, B6, B4 = "head", "B2", "B3", "B5", "B6", "B4"
STEP_NAMES = (HEAD, B2, B3, B5, B6, B4)
# The ROM's start of each slice after the head: where our previous slice's exit arrives (the head's: its own end).
ROM_STARTS = {B2: boot.HEAD_ENDS, B3: boot.HARDWARE_INIT_CALLED, B5: boot.IKBD_RESET_DONE, B6: boot.INTERRUPTS_OPENED,
              B4: boot.MIDBOOT}
SLICE_STARTS = frozenset({boot.RESET_PC, *ROM_STARTS.values()})
END = boot_launch.GEM_ENTRY


def blob():
    return boot_sysvars.product()


def entries():
    """`{step: our entry}` — each product's own, read off its symbols."""
    the_blob = blob()
    return {B2: the_blob.entry(boot_sysvars.ENTRY_SYMBOL),
            B3: the_blob.entry(boot_hwinit.ENTRY_SYMBOL[boot_hwinit.STRETCH_KIND]),
            B5: boot_display.product().base, B6: boot_late.product().base,
            B4: boot_launch.our_entry(boot_launch.SliceOf(boot_launch.LAUNCH, DISK))}


def products():
    """`{name: (base, bytes)}` of every product of ours the chain lays."""
    the_blob = blob()
    return {"head": boot_head.product(), "blob": (the_blob.base, the_blob.blob),
            "display": (boot_display.product().base, boot_display.product().code),
            "late": (boot_late.product().base, boot_late.product().code),
            "launch": (boot_launch.product().base, boot_launch.product().code)}


def exits(base, code):
    """`{target: count}`: every word-aligned `jmp.l` in `code` (laid at `base`) into the ROM window."""
    found = {}
    for at in range(0, len(code) - LONG_BYTES - WORD_BYTES + 1, WORD_BYTES):
        opcode, target = struct.unpack_from(">HI", code, at)
        if opcode == JMP_ABSOLUTE_LONG and boot.ROM_WINDOW[0] <= target < boot.ROM_WINDOW[1]:
            found[target] = found.get(target, 0) + 1
    return found


# THE BLOB'S BOOT ENTRIES, the only part of it the link check scans (the blob is every core of the build: its other
# `jmp.l`s into the ROM are no boot slice's) — each entry to the first symbol above it that is not one of its own labels.
BLOB_BOOT_ENTRIES = {boot_sysvars.ENTRY_SYMBOL: (),
                     boot_hwinit.ENTRY_SYMBOL[boot_hwinit.STRETCH_KIND]: (boot_hwinit.RETURNED_SYMBOL,)}
# EVERY `jmp.l` INTO THE ROM WINDOW EACH PRODUCT HOLDS, exactly (read off the code, `test_boot_chain.py`): B2's entry its
# `jmp $fc03b6`, B3's called entry its `jmp $fc03e0`; the display's `jmp $fc0452` on each of its two paths (colour, mono)
# and its `jmp $fc0e1a` into the sync wait (the mono switch's, R-B5-1: no slice start); the late C's `jmp $fc047a`; the
# launch's `jmp $fc0030` (the ROM's own, after a GEM that returned: no chain's). The head holds none: it is the ROM's
# head transcribed to its last byte and FALLS THROUGH at its end.
EXPECTED_EXITS = {"head": {}, "blob": {boot.HARDWARE_INIT_CALLED: 1, boot.IKBD_RESET_DONE: 1},
                  "display": {boot.INTERRUPTS_OPENED: 2, boot_display.SYNC_WAIT: 1}, "late": {boot.MIDBOOT: 1},
                  "launch": {boot.RESET_PC: 1}}


def _blob_boot_code(base, code):
    """`(base, code)` of each of the blob's boot entries in the blob `code` laid at `base`, as `exits` scans it."""
    symbols = blob().symbols
    out = []
    for symbol, own_labels in BLOB_BOOT_ENTRIES.items():
        lo = symbols[symbol]
        inner = {symbols[label] for label in own_labels}
        hi = min(at for at in symbols.values() if at > lo and at not in inner)
        out.append((lo, code[lo - base:hi - base]))
    return out


def product_exits(name, laid):
    """`exits` of product `name` of `laid` — the blob's over its boot entries alone."""
    if name != "blob":
        return exits(*laid[name])
    found = {}
    for base, code in _blob_boot_code(*laid["blob"]):
        for target, count in exits(base, code).items():
            found[target] = found.get(target, 0) + count
    return found


def steering():
    """THE STEERING MAP, `{the ROM's slice start our previous slice arrives at: our next entry}` — the head's fall-through
    at its own end into B2's entry, and every other key a ROM address some product's exit jumps to (`link_check`)."""
    ours = entries()
    return {boot_head.ours(boot.HEAD_ENDS): ours[B2], **{ROM_STARTS[step]: ours[step] for step in (B3, B5, B6, B4)}}


def link_check(steering_map=None, laid=None):
    """THE STATIC LINK CHECK (R-CH-1's (d)): every `jmp.l` into the ROM window each product holds, exactly as named
    (`EXPECTED_EXITS`, a multiset — so a re-targeted exit or an added one is named, a slice start or not); the head is
    exactly the head's length (its fall-through at its end); and the steering map is exactly the arrivals: the head's end
    and the slice starts the products exit to, each into that step's entry. `[]` = held, else each by name. (Which
    product exits to which start is the exact multiset's to hold: a presence check beside it would be redundant.)"""
    steering_map = steering() if steering_map is None else steering_map
    laid = products() if laid is None else laid
    held = {name: product_exits(name, laid) for name in EXPECTED_EXITS}
    found = [f"{name}: exits {_targets(held[name])}, not {_targets(EXPECTED_EXITS[name])}" for name in EXPECTED_EXITS
             if held[name] != EXPECTED_EXITS[name]]
    head_base, head_code = laid["head"]
    if head_base + len(head_code) != boot_head.ours(boot.HEAD_ENDS):
        found.append(f"head: ends at {head_base + len(head_code):#x}, not at its fall-through {boot_head.ours(boot.HEAD_ENDS):#x}")
    ours = entries()
    starts = {ROM_STARTS[step]: step for step in (B3, B5, B6, B4)}
    exited = {target for each in held.values() for target in each if target in starts}
    expected = {boot_head.ours(boot.HEAD_ENDS): ours[B2], **{target: ours[starts[target]] for target in sorted(exited)}}
    if steering_map != expected:
        found.append(f"the steering map {_hex(steering_map)} is not the products' {_hex(expected)}")
    return found


def _targets(counted):
    return {f"{target:#x}": count for target, count in sorted(counted.items())}


def _hex(mapping):
    return {f"{key:#x}": f"{value:#x}" for key, value in mapping.items()}


def steered(machine, arrived_at, steering_map):
    """THE STEERING: `machine` — which must stand at `arrived_at`, refused by name otherwise — entered at our next entry."""
    standing = machine.registers["pc"]
    if standing != arrived_at:
        raise boot.Refused(f"{machine.label}: the chain stands at {standing:#x}, not at {arrived_at:#x} where it steers")
    return boot.entered_at(machine, steering_map[arrived_at])


# ---- WHAT A RUN SPENT WHERE (read off each leg's profile) ---------------------------------------------------------------
def _symbol_extent(symbol, symbols=None):
    """`(lo, hi)`: the blob's `symbol` to the next symbol above it."""
    symbols = blob().symbols if symbols is None else symbols
    lo = symbols[symbol]
    return lo, min(at for at in symbols.values() if at > lo)


def _rom_dispatcher_jsr_return():
    """The ROM's dispatcher's `jsr (a0)` return — read off its text, `[XBIOS_TRAP14, BIOS_FUNCTION_TABLE)`."""
    image = boot.BASE_IMAGE
    at = next(at for at in range(addrs.XBIOS_TRAP14, addrs.BIOS_FUNCTION_TABLE, WORD_BYTES)
              if struct.unpack_from(">H", image, at)[0] == JSR_INDIRECT_A0)
    return at + WORD_BYTES


def _our_dispatcher_jsr_return():
    lo, hi = _symbol_extent("trap_dispatch_common")
    code = blob().blob
    at = next(at for at in range(lo, hi, WORD_BYTES)
              if struct.unpack_from(">H", code, at - blob().base)[0] == JSR_INDIRECT_A0)
    return at + WORD_BYTES


OUR_HBL = boot_sysvars.LINKED[addrs.VECTOR_HBL][0]
OTHER_LINKED = {**{vector: link for vector, link in boot_sysvars.LINKED.items()
                   if vector not in (addrs.VECTOR_HBL, addrs.VECTOR_TRAP_BIOS, addrs.VECTOR_TRAP_XBIOS)},
                **boot_hwinit.LINKED}


@functools.cache
def spans():
    """`{name: ((lo, hi), ...)}`: every span a leg's cycles are read in."""
    the_blob = blob()
    symbols = the_blob.symbols
    trap_lo, trap_hi = symbols["xbios_trap14"], _symbol_extent("trap_dispatch_common")[1]
    return {
        **{f"our {name}": ((base, base + len(code)),) for name, (base, code) in products().items()},
        "the ROM's head": (boot.THE_ROM_S_HEAD,),
        "the ROM's B2": boot_sysvars.THE_ROM_S_SPANS,
        "the ROM's window": (boot.ROM_WINDOW,),
        "the hooks": (boot_hwinit.HOOKS,),
        "the ROM's B3": (boot_hwinit.STRETCH, (boot_hwinit.CALLED, boot_hwinit.CONSTANTS["ROM_HWINIT_RTS"] + WORD_BYTES)),
        "the ROM's B5": (boot_display.SPAN,),
        "the ROM's B6": boot_late.THE_ROM_S_SPANS,
        "the ROM's B4": boot_launch.THE_ROM_S_SPANS,
        # THE LINKED HANDLERS AND THEIR ROM COUNTERPARTS: the trap dispatcher (ours `trap.S`, the ROM's up to its table)
        # and the HBL (`isr.S`'s, byte for byte the ROM's, which the VBL's entry follows).
        "our trap.S": ((trap_lo, trap_hi),),
        "our trap leas": ((symbols["xbios_trap14"], symbols["xbios_trap14"] + LEA_ABSOLUTE_LONG_BYTES),
                          (symbols["bios_trap13"], symbols["bios_trap13"] + LEA_ABSOLUTE_LONG_BYTES)),
        "the ROM's dispatcher": ((addrs.XBIOS_TRAP14, addrs.BIOS_FUNCTION_TABLE),),
        "the ROM's trap leas": ((addrs.XBIOS_TRAP14, addrs.XBIOS_TRAP14 + LEA_PC_RELATIVE_BYTES),
                                (addrs.BIOS_TRAP13, addrs.BIOS_TRAP13 + LEA_PC_RELATIVE_BYTES)),
        "our HBL": (_symbol_extent(OUR_HBL),),
        "the ROM's HBL": ((addrs.ISR_HBL, addrs.ISR_VBL),),
        # ...and the linked entries NO chain enters (no VBL, timer C, ACIA interrupt, no Line-A): ours, by symbol.
        "our other linked entries": tuple(_symbol_extent(symbol) for symbol, _rom in OTHER_LINKED.values()),
    }


OUR_PRODUCTS = ("our head", "our blob", "our display", "our late", "our launch")


def _read():
    return {name: sum(emu.prof_cycles(lo, hi) for lo, hi in each) for name, each in spans().items()}


def _added(one, other):
    return {name: one.get(name, 0) + other.get(name, 0) for name in {*one, *other}}


def _leg(machine, stops, laid=None, **declared):
    """One `boot.run`, profiled: `(Slice, {span: cycles})` — the profile read AFTER it is disabled, and the spans made
    BEFORE it is enabled (their first making loads the blob, whose construction runs the oracle: it would be counted)."""
    spans()
    if laid:
        done = boot.run(machine, stops, laid=laid, **declared)      # (profiles, and disables, itself)
        return done, _read()
    emu.prof_enable(True)
    emu.prof_reset()
    try:
        done = boot.run(machine, stops, **declared)
    finally:
        emu.prof_enable(False)
    return done, _read()


# ---- ONE STEP, ONE SHORE ---------------------------------------------------------------------------------------------------
Step = namedtuple("Step", "name machine stop instructions cycles stored ledgers spent answers carry", defaults=(None,))
Step.__doc__ = """One shore's run of one step: the `machine` it left (at gem_entry: the launch's RAM and registers), the `stop`,
its `instructions` and `cycles`, the RAM it `stored` (address runs), its ordered `ledgers` (`{name: tuple}`), what it
`spent` in each span (`spans`), the `answers` it was given (B5's poll, B6's ledger), and the `carry` it hands the next
step (R-D4-2: PSG port A and the FDC/DMA chip, `boot_late.Carry`). B6's ledgers hold the FDC model's ledger and the chip it
left (`fdc_events`, `fdc_chip`): compared exactly at its boundary."""
SLICE_LEDGERS = boot_hwinit.LEDGERS
LAUNCH_LEDGERS = ("io_reads", "hardware_reads", "hardware_writes", "gemdos", "calls", "blanks", "clock", "disk")


def _joined_step(name, legs, spent, carry, answers=()):
    joined = legs[0]
    for later in legs[1:]:
        joined = boot_hwinit.joined(joined, later)
    return Step(name, joined.machine, joined.stop, joined.instructions, joined.cycles, joined.stored,
                {**{ledger: getattr(joined, ledger) for ledger in SLICE_LEDGERS}, "fdc_chip": joined.fdc_chip}, spent,
                tuple(answers), carry)


def _carried_through(legs, carry):
    """The carry after `legs` that do NOT arm the FDC model: port A after their stores, the chip unchanged (no slice
    before B6 touches the FDC: `test_boot_chain.py` holds their ledgers clear of the DMA block)."""
    for done in legs:
        carry = carry._replace(port_a=boot.port_a_after(done, carry.port_a))
    return carry


def _answered_legs(machine, until, laid, mono, observing, floppy=None, **declared):
    """`machine` run to `until` leg by leg — a stop at B5's poll answered (R-B5-1), at one of B6's waits answered (D3,
    R-B4-2), at an observed entry (where `observing`) ledgered and run on: `(legs, spent, answers, carry)`. `floppy`:
    `(drives, carry, gpip)` — every leg through the FDC model, the carry handed leg to leg (B6's); else None."""
    stops = {until} | (boot_late.ANSWERED if not mono else boot_late.ANSWERED | {boot_display.SYNC_POLL})
    stops |= boot_late.OBSERVED if observing else frozenset()
    legs, spent, answers = [], {}, []
    carry = floppy[1] if floppy else None
    while True:
        leg_declared = {**declared, **boot_late.floppy_declared(floppy[0], carry, floppy[2])} if floppy else declared
        done, cycles = _leg(machine, stops, laid, **leg_declared)
        if floppy:
            carry = boot_late.carried(done, carry)
        legs.append(done)
        spent = _added(spent, cycles)
        if done.stop == until:
            return legs, spent, answers, carry
        if done.stop == boot_display.SYNC_POLL:
            machine = boot_display.answered_poll(done.machine)
            answers.append(("the sync wait's poll",))
        elif done.stop in boot_late.OBSERVED:
            machine = done.machine
            answers.append(boot_late.observed(machine))
        else:
            machine, asked, runs = boot_late.answered(done.machine)
            answers.append(asked)
            legs[-1] = done._replace(stored=(*done.stored, *runs))


def _answered_step(name, machine, until, laid, mono, carry, floppy=None, **declared):
    """A step through its answered entries: THE PLAIN RUN for the machine and the price, THE WATCHED RUN (the observed
    entries stops too) for the answer ledger — held to leave the same machine (B6's rule: a resumed stop counts its
    step-off again). `floppy`: `(drives, gpip)` — B6's, through the FDC model, `carry` handed leg to leg."""
    through = (floppy[0], carry, floppy[1]) if floppy else None
    legs, spent, answers, left = _answered_legs(machine, until, laid, mono, observing=False, floppy=through, **declared)
    watched, _spent, ledger, _left = _answered_legs(machine, until, laid, mono, observing=True, floppy=through, **declared)
    if (watched[-1].machine, watched[-1].fdc_chip) != (legs[-1].machine, legs[-1].fdc_chip):
        raise boot.Refused(f"{machine.label}: the step {name} watched is not the step unwatched")
    return _joined_step(name, legs, spent, left if floppy else _carried_through(legs, carry), ledger)


def _launch_step(machine, laid, carry):
    """B4 through `boot_launch.run` — the floppy answered at the upper driver's entries there (R-D4-3: `aes_boot.Floppy`
    stays everywhere but B6): the FDC model is not armed, so the chip passes through as B6 left it."""
    launch, _elsewhere = boot_launch.run(machine, boot_launch.disk(DISK).image, END, (), laid=laid)
    spent = _read()
    left = machine._replace(ram=launch.ram, registers=launch.registers)
    return Step(B4, left, launch.stop, launch.instructions, launch.cycles, launch.stored,
                {ledger: getattr(launch, ledger) for ledger in LAUNCH_LEDGERS}, spent, (), carry)


def _labelled(machine, chain):
    label = f"{machine.label}; {boot_display.label_of(chain.arm)}; {boot_late.ANSWER_LABEL}; {CHAINED_LABEL}"
    return machine._replace(label=label)


# THE CARRY FROM THE RESET (R-D4-2): port A not yet stored (the head's first store sets it, on both shores — refused by
# name otherwise), the FDC chip MR's (None: `emu`'s power-on chip, which every armed run is handed in its place).
RESET_CARRY = boot_late.Carry(None, None)


def _b3_declared(carry):
    """B3's declarations IN THE CHAIN: its battery's, but PSG port A the one CARRIED from the head's own store
    (R-D4-2) — not the seed its battery declares, which stays that battery's alone."""
    if carry.port_a is None:
        raise boot.Refused("the chain reached B3 with PSG port A never stored: nothing to carry")
    declared = boot_hwinit.declared()
    return {**declared, "psg_seed": {**declared["psg_seed"], addrs.PSG_PORT_A: carry.port_a}}


def _b3_legs(machine, first_stop, carry):
    """B3's two legs, port A carried into the first and from it into the second: `(first, second, spent, carry)`."""
    first, spent_first = _leg(machine, {first_stop}, **_b3_declared(carry))
    carry = _carried_through([first], carry)
    second, spent_second = _leg(first.machine, {boot.IKBD_RESET_DONE}, **_b3_declared(carry))
    return first, second, _added(spent_first, spent_second), _carried_through([second], carry)


@functools.cache
def _rom_to_interrupts_opened(chain, with_the_blob=True):
    """The ROM's head, B2, B3 and B5 on `chain`: `(steps, the carry at $fc0452)`."""
    machine = _labelled(boot_head.ARMS[chain.machine](), chain)
    steps = []
    done, spent = _leg(machine, {boot.HEAD_ENDS})
    carry = _carried_through([done], RESET_CARRY)
    steps.append(_joined_step(HEAD, [done], spent, carry))
    machine = boot_sysvars.laid(done.machine) if with_the_blob else done.machine
    done, spent = _leg(machine, {boot.HARDWARE_INIT_CALLED})
    carry = _carried_through([done], carry)
    steps.append(_joined_step(B2, [done], spent, carry))
    first, second, spent, carry = _b3_legs(done.machine, boot_hwinit.RETURNED, carry)
    steps.append(_joined_step(B3, [first, second], spent, carry))
    mono = chain.arm.monitor == boot_display.MONO
    steps.append(_answered_step(B5, second.machine, boot.INTERRUPTS_OPENED, None, mono, carry,
                                **boot_display.declared(chain.arm)))
    return tuple(steps), steps[-1].carry


def rom_port_a_entering_b6(chain):
    """PSG port A at `$fc0452` on `chain`, off the ROM's own chained runs (`boot_late.port_a_at_start`'s source)."""
    return _rom_to_interrupts_opened(chain)[1].port_a


def _floppy(chain):
    """B6's floppy in the chain: the capture's drives, GPIP's other bits the chain's B5 arm's."""
    return boot_late.drives(boot_late.CAPTURE_DRIVES), boot_display.GPIP_OF[chain.arm.monitor]


@functools.cache
def the_rom_s(chain, with_the_blob=True):
    """THE ROM'S OWN BOOT on `chain`, step by step from the reset: `(Step, ...)`. The bench blob is laid at `$fc02cc` as on
    ours (`with_the_blob`; held equal without it outside its span). PSG port A and the FDC chip carried at every
    boundary from the ROM's own runs; B6 through the FDC model."""
    steps, carry = _rom_to_interrupts_opened(chain, with_the_blob)
    steps = list(steps)
    steps.append(_answered_step(B6, steps[-1].machine, boot.MIDBOOT, None, False, carry, floppy=_floppy(chain)))
    steps.append(_launch_step(steps[-1].machine, None, steps[-1].carry))
    return tuple(steps)


@functools.cache
def ours(chain, steering_map=None):
    """OUR BOOT on `chain`: the head from our reset, each later slice of ours ENTERED by the steering at the arrival of the
    one before (`steered`), on its own staging — `(Step, ...)`. `steering_map`: a case's own (a negative's lever), as
    `tuple(items)`; the products' by default."""
    steering_map = steering() if steering_map is None else dict(steering_map)
    the_blob = blob()
    machine = _labelled(boot_head.ours_of(boot_head.ARMS[chain.machine]()), chain)
    steps = []
    done, spent = _leg(machine, {boot_head.ours(boot.HEAD_ENDS)}, laid=boot_head.overlay())
    carry = _carried_through([done], RESET_CARRY)
    steps.append(_joined_step(HEAD, [done], spent, carry))
    machine = steered(boot_sysvars.laid(done.machine), boot_head.ours(boot.HEAD_ENDS), steering_map)
    done, spent = _leg(machine, {boot.HARDWARE_INIT_CALLED})
    carry = _carried_through([done], carry)
    steps.append(_joined_step(B2, [done], spent, carry))
    machine = steered(done.machine, boot.HARDWARE_INIT_CALLED, steering_map)
    first, second, spent, carry = _b3_legs(machine, the_blob.entry(boot_hwinit.RETURNED_SYMBOL), carry)
    steps.append(_joined_step(B3, [first, second], spent, carry))
    mono = chain.arm.monitor == boot_display.MONO
    machine = steered(second.machine, boot.IKBD_RESET_DONE, steering_map)
    steps.append(_answered_step(B5, machine, boot.INTERRUPTS_OPENED, boot_display.overlay(), mono, carry,
                                **boot_display.declared(chain.arm)))
    machine = steered(steps[-1].machine, boot.INTERRUPTS_OPENED, steering_map)
    steps.append(_answered_step(B6, machine, boot.MIDBOOT, boot_late.overlay(), False, steps[-1].carry,
                                floppy=_floppy(chain)))
    machine = steered(steps[-1].machine, boot.MIDBOOT, steering_map)
    steps.append(_launch_step(machine, boot_launch.overlay(), steps[-1].carry))
    _vet_who_ran(machine.label, steps)
    return tuple(steps)


# ---- WHO RAN, AND EACH SHORE'S OWN ---------------------------------------------------------------------------------------
def rom_own(step):
    """The ROM's OWN cycles in `step`: its ported spans — B3's its whole run in the ROM window but the hooks, as B3 prices
    it — and, in every step, its own dispatcher and HBL handler, the counterparts of our linked entries."""
    spent = step.spent
    linked = spent["the ROM's dispatcher"] + spent["the ROM's HBL"]
    if step.name == B3:
        return spent["the ROM's window"] - spent["the hooks"]
    ported = {HEAD: "the ROM's head", B2: "the ROM's B2", B5: "the ROM's B5", B6: "the ROM's B6", B4: "the ROM's B4"}
    return spent[ported[step.name]] + linked


# THE PRODUCT EACH STEP LAYS beside the blob: an overlay's span is the ROM's own text in every other step (the head's lies
# over GEMDOS's file system, which the launch runs: 1,782 cycles — D10's first item owed), so it is ours in its own step only.
OVERLAY_OF = {HEAD: "head", B2: None, B3: None, B5: "display", B6: "late", B4: "launch"}


def our_own(step):
    """OUR OWN cycles in `step`: every cycle in the blob and in the overlay the step lays."""
    overlay = OVERLAY_OF[step.name]
    return step.spent["our blob"] + (step.spent[f"our {overlay}"] if overlay else 0)


# EVERY ROM SPAN THE BOOT PORTS, whichever step's: the head, B2 (with `$fc0eba`), B3's stretch and `$fc2408`, B5, B6 (with
# its five routines), B4 (the launch and the AUTO runner), and the counterparts of our linked entries.
PORTED_UNION = ("the ROM's head", "the ROM's B2", "the ROM's B3", "the ROM's B5", "the ROM's B6", "the ROM's B4",
                "the ROM's dispatcher", "the ROM's HBL")


def _vet_who_ran(label, steps):
    """A CHAINED RUN OF OURS NEVER RUNS THE ROM'S CODE IT PORTS — read off each step's profile, REFUSED BY NAME: no cycle in
    the step's own ported code (`rom_own`: B3's its whole window but the hooks), NONE IN ANY SPAN THE BOOT PORTS, whichever
    step's (`PORTED_UNION`: ours that called into another slice's ROM text would pass a vet of its own step alone), and no
    entry of a linked handler no chain takes. Ours that fell into the ROM's own would be measured equal on the ROM's
    instructions; a vector left the ROM's would run its dispatcher here."""
    for step in steps:
        if rom_own(step):
            raise boot.Refused(f"{label}: our step {step.name} ran {rom_own(step)} cycles of the ROM's own code it ports")
        ported = {name: step.spent[name] for name in PORTED_UNION if step.spent[name]}
        if ported:
            raise boot.Refused(f"{label}: our step {step.name} ran the ROM's ported code {ported}")
        if step.spent["our other linked entries"]:
            raise boot.Refused(f"{label}: our step {step.name} entered a linked entry no chain takes")


# ---- WHAT IS HELD -----------------------------------------------------------------------------------------------------------
# THE CARRIES, EXACTLY (the registers ours leaves apart from the ROM's at each boundary, each a slice's named scratch):
# B2's (`boot_sysvars.NOT_HELD`: D1, A1, A3, A4) at $fc03b6; B3's stretch (`boot_hwinit.NOT_HELD`: D1, A1, D2, A2) and B2's
# A4, carried, at $fc03e0. NONE past $fc0452: the ROM's routines B5 calls lay every one of them on both shores.
CARRIED = {B2: frozenset({"d1", "a1", "a3", "a4"}), B3: frozenset({"d1", "a1", "d2", "a2", "a4"}), HEAD: frozenset(),
           B5: frozenset(), B6: frozenset(), B4: frozenset()}


# THE BIOS STACK'S DEAD FRAMES, TIGHTENED FOR THE CHAIN (its comparison alone; the slices' batteries keep their own
# classes). At `$fc047a` the two shores' frames — B3's, B5's, B6's, each at its own depth — differ only from `$74ff` up on
# every chain (measured, `test_boot_chain.py`): below it the mid-boot mask's field `[$745a, $755a)` is held byte for
# byte. At gem_entry the launch has stored over all of them but THREE BYTES, B3's frames' leftovers no later store reaches
# (measured: five before D4's P3 — `$7509` and `$750f` were apart then and are equal now; which of P3's changes laid them
# alike, the port-A carry or the lower floppy driver's frames, is not separated):
# the comparison there is no region at all, but that exact set (`APART_AT_THE_END`).
FRAMES_APART_FROM = 0x74ff
APART_AT_THE_END = frozenset({0x74ff, 0x7500, 0x7501})


@functools.cache
def residue(chain, name):
    """The dead stack residue at the end of step `name`: B2's (`boot_sysvars.residue_class`), B3's (carried through B5),
    B6's from `FRAMES_APART_FROM` (the mid-boot capture's MASK field, tightened); none after the head, and none at
    gem_entry, where `APART_AT_THE_END` is held exactly instead."""
    if name in (HEAD, B4):
        return None
    if name == B2:
        return boot_sysvars.residue_class(chain.machine)
    if name in (B3, B5):
        return boot_hwinit.residue_class(chain.machine, boot_hwinit.STRETCH_KIND)
    return FRAMES_APART_FROM, boot_late.STACK_RESIDUE[1]


APART = {B4: APART_AT_THE_END}           # the bytes a step's end is apart in, EXACTLY (set equality), outside its residue


LINKED = {**boot_sysvars.LINKED, **boot_hwinit.LINKED}


def our_returns():
    """`{our address: the ROM's}` — THE RETURN ADDRESSES INTO OUR CODE that dead frames keep: our dispatcher's `jsr (a0)`
    return for the ROM's; every address of the launch's overlay for the ROM's by offset (the .S lays the ROM's bytes at
    their own offsets: `boot_launch`)."""
    return {_our_dispatcher_jsr_return(): _rom_dispatcher_jsr_return()}


def _launch_rom_address(value):
    lo, hi = boot_launch.our_span()
    return boot_launch.LAUNCH_SPAN[0] + value - lo if lo <= value < hi else None


def _pre_init_mask_words(length):
    """Every word-aligned address a longword can be read at inside the pre-init MASK's fields."""
    return sorted({at for base, size, _name in preinit_snapshot.MASK
                   for at in range(base + base % WORD_BYTES, min(base + size, length - LONG_BYTES + 1), WORD_BYTES)})


def returns_mapped(ram, returns=None):
    """`ram` with every return into our code that a dead frame INSIDE THE PRE-INIT MASK keeps given the ROM's: a longword
    (word-aligned) holding one, or — where a later frame overwrote its high word — the low word of our dispatcher's."""
    returns = our_returns() if returns is None else returns
    mapped = bytearray(ram)
    low_words = {ours & 0xffff: rom & 0xffff for ours, rom in returns.items()}
    for at in _pre_init_mask_words(len(ram)):
        value = struct.unpack_from(">I", ram, at)[0]
        rom = returns.get(value, _launch_rom_address(value))
        if rom is not None:
            struct.pack_into(">I", mapped, at, rom)
            continue
        word = value >> 16
        if word in low_words and not _in_our_code(struct.unpack_from(">I", ram, at - WORD_BYTES)[0]):
            struct.pack_into(">H", mapped, at, low_words[word])
    return bytes(mapped)


def _in_our_code(value):
    return any(lo <= value < hi for name, each in spans().items() if name in OUR_PRODUCTS for lo, hi in each)


def ram_held(step):
    """Our megabyte at the end of `step` as the ROM's is compared to: the linked vectors mapped back, and at gem_entry the
    launch's links and the returns into our code inside the pre-init mask."""
    ram = boot_sysvars.mapped_back(step.machine.ram, blob().symbols, LINKED)
    if step.name == B4:
        ram = returns_mapped(boot_launch.mapped_back(ram, boot_launch.linked(boot_launch.LAUNCH)))
    return ram


# THE STEPS THE HEAD'S LINKS LIVE THROUGH: A6 holds the head's last link until B6's ACSI answer lays it.
HEAD_LINKS_LIVE = (HEAD, B2, B3, B5)


def registers_held(step):
    """Our registers at the end of `step` as the ROM's are compared to: the head's links (PC, A6) by offset back to the
    ROM's while they live (`HEAD_LINKS_LIVE`: from B6 on its laid span is the ROM's own text — GEMDOS's — and an address
    there is the ROM's), and the mono arm's link to the sync wait (B5's)."""
    registers = dict(step.machine.registers)
    if step.name == B5:
        registers = boot_display.mapped_registers(registers)
    if step.name not in HEAD_LINKS_LIVE:
        return registers
    head_lo = boot_head.LAID_AT
    head_hi = head_lo + boot_head.HEAD_HI - boot_head.HEAD_LO
    return {name: (value - head_lo + boot_head.HEAD_LO if name in boot_head.LINKS and head_lo <= value <= head_hi else value)
            for name, value in registers.items()}


def _outside(ram, span):
    if span is None:
        return ram
    lo, hi = span
    return ram[:lo] + bytes(hi - lo) + ram[hi:]


def _stored_outside(step, span):
    lo, hi = span or (0, 0)
    return {at for start, length in step.stored for at in range(start, start + length) if not lo <= at < hi}


def stop_held(step):
    return boot.HEAD_ENDS if step.stop == boot_head.ours(boot.HEAD_ENDS) else step.stop


def differences(rom, mine, chain):
    """Every surface our `mine` (a step) differs from the ROM's `rom` on, by name (none: held): the stop, the registers
    but the step's CARRIED (exactly them: a carry gone, or a new one, is named too), the megabyte outside the step's
    residue with the named mappings, the addresses stored outside it, every ledger, the answers."""
    found = []
    if stop_held(mine) != rom.stop:
        found.append(f"stop: the ROM's {rom.stop:#x}, ours {mine.stop:#x}")
    theirs, yours = rom.machine.registers, registers_held(mine)
    apart = {name for name in theirs if theirs[name] != yours[name]}
    if apart != CARRIED[mine.name]:
        found.append(f"registers apart {sorted(apart)}, the carries named {sorted(CARRIED[mine.name])}")
    span = residue(chain, mine.name)
    rom_ram, our_ram = _outside(rom.machine.ram, span), _outside(ram_held(mine), span)
    if rom_ram != our_ram or APART.get(mine.name):
        apart = {at for at, (one, other) in enumerate(zip(rom_ram, our_ram)) if one != other}
        if apart != APART.get(mine.name, frozenset()):
            found.append(f"ram, first at {min(apart ^ APART.get(mine.name, frozenset())):#x}")
    if _stored_outside(rom, span) != _stored_outside(mine, span):
        found.append("stored: the addresses stored outside the residue differ")
    for ledger in rom.ledgers:
        if rom.ledgers[ledger] != mine.ledgers[ledger]:
            found.append(f"{ledger}: the ROM's and ours differ")
    if rom.answers != mine.answers:
        found.append(f"answers: the ROM's {rom.answers}, ours {mine.answers}")
    if rom.carry != mine.carry:
        found.append(f"carry: the ROM's {rom.carry}, ours {mine.carry}")
    return found


# ---- THE END SURFACES (COLD: the captures are a power-on's) ------------------------------------------------------------------
# AT gem_entry against the pre-init capture of the blank disk: D1's memctrl, and the lower floppy driver's own state the
# LAUNCH never lays — B6 now leaves it the capture's (the driver run through the FDC model, R-D4-3), but B4 answers the
# floppy at the upper driver's entries (`aes_boot.Floppy`, which R-D4-3 keeps there), so the reads Hatari's launch made
# through the lower driver (its request, its save area, its records) are on no shore: this exact set, measured.
END_PREINIT_MEMCTRL = (boot_late.MEMCTRL_COPIES[0],)
END_PREINIT_LOWER_DRIVER = (0xa0d, 0xa0f, 0xa14, 0xa15, 0xa2a, 0xa2b, 0xa2e, 0xa2f, 0xa31, 0xa33, 0xa35, 0xa37, 0xa39,
                            0xa3b, 0xa3d, 0xa3e, 0xa3f, 0xa42, 0xa43, 0xa46, 0xa47, 0xa4a, 0xa4b)


def against_the_midboot(step, capture, ours_side):
    """`(registers, addresses)` apart from the mid-boot capture at `$fc047a`, outside its MASK and the blob's span."""
    ram = boot_sysvars.mapped_back(step.machine.ram, blob().symbols, LINKED) if ours_side else step.machine.ram
    span = (blob().base, blob().end)
    registers = {name for name in capture.registers if capture.registers[name] != step.machine.registers[name]}
    mine, theirs = midboot_snapshot.masked(_outside(ram, span)), midboot_snapshot.masked(_outside(capture.ram, span))
    return registers, {at for at, (one, other) in enumerate(zip(mine, theirs)) if one != other}


def against_the_preinit(step, capture, ours_side):
    """`(registers, addresses)` apart from the pre-init capture at gem_entry, outside its MASK and the blob's span."""
    ram = ram_held(step) if ours_side else step.machine.ram
    span = (blob().base, blob().end)
    registers = {name for name in boot.REGISTER_NAMES if capture.registers[name] != step.machine.registers[name]}
    mine, theirs = preinit_snapshot.masked(_outside(ram, span)), preinit_snapshot.masked(_outside(capture.ram, span))
    return registers, {at for at, (one, other) in enumerate(zip(mine, theirs)) if one != other}


# ---- THE HAND-OFF NO SLICE SEES: the calls through the linked trap vectors, counted -------------------------------------------
def trap_calls(step, ours_side):
    """The BIOS/XBIOS traps `step` took through the dispatcher: its first instruction's cycles over that `lea`'s."""
    if ours_side:
        return step.spent["our trap leas"] // LEA_ABSOLUTE_LONG_CYCLES
    return step.spent["the ROM's trap leas"] // LEA_PC_RELATIVE_CYCLES


# ---- THE PRICE (ruling D9: each shore's own cycles; the rest held equal step by step) --------------------------------------
Shore = namedtuple("Shore", "steps instructions cycles")
Priced = namedtuple("Priced", "the_rom_s ours own rest")
Priced.__doc__ = """A chain measured on both shores: the two `Shore`s (their `instructions`, summed over the steps), `own`
(ours every cycle in our products and blob, the ROM's in its ported spans and its dispatcher and HBL handler) and `rest`
(each run's other cycles: the ROM's code both run, the answers' runs), held equal in every step."""


def _shore(steps):
    return Shore(steps, sum(step.instructions for step in steps), sum(step.cycles for step in steps))


def priced(chain):
    """`chain` PRICED: both shores run, every held surface equal at every boundary (refused by name otherwise), the rest
    beside each shore's own equal in every step. Our run is the last made: its profile is the one left."""
    rom = the_rom_s(chain)
    mine = ours.__wrapped__(chain)
    for one, other in zip(rom, mine):
        found = differences(one, other, chain)
        assert not found, f"{chain}: at the end of {other.name} ours differs from the ROM's — {'; '.join(found)}"
        rests = (other.cycles - our_own(other), one.cycles - rom_own(one))
        assert rests[0] == rests[1], f"{chain}: in {other.name}, beside its own, ours spent {rests[0]} cycles, the ROM's {rests[1]}"
    own = (sum(our_own(step) for step in mine), sum(rom_own(step) for step in rom))
    rest = sum(step.cycles for step in mine) - own[0]
    return Priced(_shore(rom), _shore(mine), own, rest)


def name_of(chain):
    return next(name for name, each in SLICES.items() if each == chain)
