#!/usr/bin/env python3
"""How much of a game can a memory-only differential harness actually verify?

Reads the TSV that `tools/ghidra_scripts/HwPortabilityScan.java` dumps out of a project's Ghidra
DB and sorts every function into portability tiers, then closes the tiers over the call graph.
Game-agnostic: the tier rules encode what `tools/recreate_kit/oracle/shim.c` models, not what any
particular program does — and `check_shim_agreement()` re-reads shim.c's own `#define`s on every
run so this file cannot drift away from it silently.

THE TIERS, and why they are the ones that matter (shim.c, "memory callbacks"):

  T0 CLEAN            no off-image access at all. The differential sees everything it does.
  T1 PSG_WRITE_ONLY   only byte writes to the PSG's two canonical ports. The shim captures those
                      into an ordered (reg, val) ledger, so they ARE diffable.
  T2 HW_WRITE_ONLY    writes other hardware and never reads any. Every such write is silently
                      DROPPED, so the run completes and its memory effects are verifiable while
                      the hardware effect is invisible: verifiable-but-incomplete.
  T3 HW_READ          reads non-PSG hardware. The shim answers every such read 0 — with exactly
                      one exception, the IKBD ACIA status, answered a fixed "ready to send" — and
                      it answers identically on BOTH sides of a differential, so the diff agrees on
                      whatever that fabricated value implies. Split by what consumes it:
                        T3-STEER  a conditional branch depends on it: FALSELY GREEN, the
                                  dangerous tier (BuggyBoy's $ffff820a music-tempo branch).
                        T3-DATA   the value is only stored or discarded: merely incomplete.
  T4 HARD_REJECT      an access to the PSG block the shim refuses outright — any read, any
                      non-byte access, any odd-alias write. `emu.run` rejects the whole run.
  T5 UNMEASURABLE     inside a region named by --exclude: code that cannot be read statically
                      at all (self-decrypting protection), so there is no source text to port.

A tier is a property of the CODE, not of any one run: a T4 function still returns green on a run
whose data never reaches its PSG access. Verify a tier empirically before relying on it — see
`projects/wonderboy/notes/portability_predictions.py` for the pattern.

Usage:
  hw_portability.py <scan.tsv> [--exclude LO:HI:LABEL]... [--root ADDR]... [--stub ADDR]...
                    [--model BLOCK:read|write]... [--subsystems FILE] [--extra-hw FILE]
                    [--title TEXT]

  --exclude     a byte range whose contents cannot be read statically -> T5. Repeatable.
  --root        entry point to close the call graph over; repeatable. Without any, every
                function is reported and "reachable" is not computed.
  --subsystems  TSV of `lo<TAB>hi<TAB>name` ranges (by function ENTRY address, FIRST match
                wins) partitioning the program; anything unmatched lands in "unclassified".
  --extra-hw    TSV of hardware sites the Ghidra scan could not see, so a known blind spot can
                be folded into the totals instead of only being described:
                `insn<TAB>hwaddr<TAB>size<TAB>dir<TAB>steer<TAB>note`. Prefer fixing the scan —
                a site Ghidra misses because it never disassembled the routine is usually cured
                by naming that routine in names.txt, which makes ApplyNames disassemble it.
  --stub        a function to treat as replaced by a harness stub: no accesses, no callees.
                Repeatable. Answers "what would stubbing X buy?" as a number rather than a guess.
  --model       `BLOCK:read` or `BLOCK:write` — pretend the harness gained a model for that
                block and direction, so such accesses stop costing a tier. Repeatable. Turns
                "which capability would unlock the most code?" into a number.

Writes a Markdown report to stdout. Exits non-zero if the scan classified nothing.
"""
import argparse
import collections
import pathlib
import re
import sys

# --- the ST I/O map, masked to the 68000's 24-bit bus (shim.c's BUS_ADDR_MASK) ----------------
BUS_ADDR_MASK = 0xFFFFFF
HW_BLOCKS = (
    (0xFF8000, 0xFF8010, "mmu"),
    (0xFF8200, 0xFF8280, "shifter"),
    (0xFF8600, 0xFF8610, "fdc_dma"),
    (0xFF8800, 0xFF8900, "psg"),
    (0xFF8900, 0xFF8940, "ste_dma_sound"),
    (0xFF8A00, 0xFF8A40, "blitter"),
    (0xFF9200, 0xFF9210, "ste_paddle"),
    (0xFFFA00, 0xFFFA40, "mfp"),
    (0xFFFC00, 0xFFFC08, "acia"),
)
# The only PSG protocol shim.c models: a BYTE write to the select latch or the data port.
PSG_SELECT, PSG_DATA = 0xFF8800, 0xFF8802
PSG_BLOCK_END = 0xFF8900
PSG_MODELED_PORTS = (PSG_SELECT, PSG_DATA)
PSG_MODELED_SIZE = 1
# The one off-image READ shim.c does not answer 0: the IKBD ACIA status reads back "transmit
# register empty" so a send loop terminates. Still a fabricated constant, so still a T3 read —
# named here because a reader who believes "every read returns 0" will mis-explain that loop.
IKBD_STATUS = 0xFFFC00

# shim.c is the authority for all four constants above. CLAUDE.md §5: a value that must agree
# across a language boundary gets ONE canonical definition and the other is pinned equal by a
# test. This module cannot import C, so it re-reads the #defines instead — see
# check_shim_agreement(), called from main().
SHIM_C = pathlib.Path(__file__).resolve().parent / "recreate_kit" / "oracle" / "shim.c"
SHIM_PINNED = {"BUS_ADDR_MASK": BUS_ADDR_MASK, "PSG_SELECT": PSG_SELECT, "PSG_DATA": PSG_DATA,
               "PSG_BLOCK_END": PSG_BLOCK_END, "IKBD_STATUS": IKBD_STATUS}

T_CLEAN, T_PSG_WRITE, T_HW_WRITE, T_HW_READ, T_HARD_REJECT, T_UNMEASURABLE = range(6)
TIER_NAMES = ["T0 CLEAN", "T1 PSG_WRITE_ONLY", "T2 HW_WRITE_ONLY", "T3 HW_READ",
              "T4 HARD_REJECT", "T5 UNMEASURABLE"]
STEER_VERDICT = "STEER"
UNATTRIBUTED_FN = "-"          # the scan's marker for code inside no function


def check_shim_agreement():
    """Fail loudly if shim.c's hardware constants no longer match this module's copies."""
    if not SHIM_C.exists():
        return                                  # a checkout without the kit: nothing to pin against
    text = SHIM_C.read_text()
    for name, mine in sorted(SHIM_PINNED.items()):
        m = re.search(r"^#define\s+%s\s+(0x[0-9a-fA-F]+|\d+)" % name, text, re.MULTILINE)
        if m is None:
            sys.exit("%s no longer defines %s — this module's tier rules claim to encode that "
                     "file's model and can no longer be checked against it." % (SHIM_C, name))
        theirs = int(m.group(1), 0)
        if theirs != mine:
            sys.exit("%s defines %s as %#x; %s has %#x. The tier rules would misclassify every "
                     "access to that block — reconcile them." % (SHIM_C, name, theirs,
                                                                 pathlib.Path(__file__).name, mine))


def hw_block(addr):
    """Name of the hardware block `addr` decodes to, or None."""
    masked = addr & BUS_ADDR_MASK
    for lo, hi, name in HW_BLOCKS:
        if lo <= masked < hi:
            return name
    return None


class Access:
    """One off-image memory access, as the oracle's shim would see it."""

    def __init__(self, fn, insn, addr, size, direction, mode, steer, stored, text, modeled=()):
        self.fn, self.insn, self.addr, self.text = fn, insn, addr, text
        self.size = None if size == "?" else int(size)
        self.is_read = direction == "READ"
        self.mode, self.steer, self.stored = mode, steer, stored == "STORED"
        self.masked = addr & BUS_ADDR_MASK
        self.block = hw_block(addr)
        # (block, direction) pairs a hypothetical harness capability covers (--model). An access
        # it covers is verifiable, so it costs no tier — which is how the cost of a missing
        # capability is priced in functions and bytes rather than argued about.
        self.modeled = modeled

    @property
    def is_covered(self):
        return (self.block, "read" if self.is_read else "write") in self.modeled

    @property
    def in_psg_block(self):
        """Does the TRANSFER touch the PSG block? shim.c's psg_block_touched() tests the whole
        access, not its first byte, so a long read straddling into $ff8800 from below is refused
        too — testing only the start address would call such a function runnable."""
        span = self.size or 1
        return self.masked < PSG_BLOCK_END and self.masked + span > PSG_SELECT

    @property
    def tier(self):
        """The tier this ONE access forces. A function takes the worst of its accesses."""
        if self.is_covered:
            return T_CLEAN
        if self.in_psg_block:
            modeled = (not self.is_read and self.masked in PSG_MODELED_PORTS
                       and self.size == PSG_MODELED_SIZE)
            return T_PSG_WRITE if modeled else T_HARD_REJECT
        return T_HW_READ if self.is_read else T_HW_WRITE

    @property
    def steers(self):
        """A read a branch depends on — the false-green case. A --model capability that answers
        the read correctly takes it out of the count."""
        if self.is_covered:
            return False
        return self.is_read and not self.in_psg_block and self.steer == STEER_VERDICT


class Function:
    def __init__(self, entry, size, body_end, name):
        self.entry, self.size, self.body_end, self.name = entry, size, body_end, name
        self.accesses = []
        self.callees = set()

    def contains(self, addr):
        """Body extent, not `entry + size`: `size` counts addressable bytes and a Ghidra body can
        be non-contiguous, so a function's last chunk can sit well past `entry + size`."""
        return self.entry <= addr < self.body_end


class Scan:
    """One parsed hw_scan TSV: functions, program facts, and the holes the scan admits to."""

    def __init__(self):
        self.funcs = {}
        self.facts = {}
        self.indirect = []           # (fn, insn, text) unresolved indirect call/jump sites
        self.orphans = []            # (start, end, insn_bytes) code in no function
        self.unattributed = []       # Accesses in code the scan attributed to no function
        self.edge_kinds = collections.Counter()


def parse_scan(path, modeled):
    scan = Scan()
    edges, pending = [], []
    for line in open(path):
        if line.startswith("#") or not line.strip():
            continue
        f = line.rstrip("\n").split("\t")
        kind = f[0]
        if kind == "P":
            scan.facts[f[1]] = f[2]
        elif kind == "F":
            scan.funcs[int(f[1], 16)] = Function(int(f[1], 16), int(f[2]), int(f[3], 16), f[4])
        elif kind == "E":
            scan.edge_kinds[f[3]] += 1
            if f[1] != UNATTRIBUTED_FN:      # an edge out of unattributed code has no source node
                edges.append((int(f[1], 16), int(f[2], 16)))
        elif kind == "I":
            scan.indirect.append((f[1], int(f[2], 16), f[3]))
        elif kind == "O":
            scan.orphans.append((int(f[1], 16), int(f[2], 16), int(f[3])))
        elif kind == "H":
            pending.append(f)
    for f in pending:
        owner = scan.funcs.get(int(f[1], 16)) if f[1] != UNATTRIBUTED_FN else None
        acc = Access(f[1], int(f[2], 16), int(f[3], 16), f[4], f[5], f[6], f[7], f[8], f[9],
                     modeled)
        (owner.accesses if owner else scan.unattributed).append(acc)
    for src, dst in edges:
        if src in scan.funcs and dst in scan.funcs and src != dst:
            scan.funcs[src].callees.add(dst)
    return scan


def apply_extra_hw(scan, path, modeled):
    """Fold hand-recorded sites (a stated blind spot) into the function that contains them."""
    added = []
    for line in open(path):
        if line.startswith("#") or not line.strip():
            continue
        insn, addr, size, direction, steer, note = line.rstrip("\n").split("\t")
        owner = next((f for f in sorted(scan.funcs.values(), key=lambda f: f.entry)
                      if f.contains(int(insn, 16))), None)
        acc = Access(UNATTRIBUTED_FN if owner is None else hex(owner.entry), int(insn, 16),
                     int(addr, 16), size, direction, "ABS", steer, "-", note, modeled)
        (owner.accesses if owner else scan.unattributed).append(acc)
        added.append(acc)
    return added


def apply_exclusions(scan, exclusions):
    """Mark every function reaching into an unreadable region — they become T5.

    Accesses inside such a region are also dropped: a "hardware access" decoded out of ciphertext
    is a decode artefact, not an access.
    """
    excluded = {}
    for f in scan.funcs.values():
        for lo, hi, label in exclusions:
            if f.entry < hi and lo < f.body_end:
                excluded[f.entry] = label
                break
    for f in scan.funcs.values():
        f.accesses = [a for a in f.accesses
                      if not any(lo <= a.insn < hi for lo, hi, _ in exclusions)]
    return excluded


def direct_tiers(scan, excluded):
    """Each function's own tier, and whether it steers on a hardware read itself."""
    tier, steers = {}, {}
    for addr, f in scan.funcs.items():
        tier[addr] = (T_UNMEASURABLE if addr in excluded
                      else max((a.tier for a in f.accesses), default=T_CLEAN))
        steers[addr] = any(a.steers for a in f.accesses)
    return tier, steers


def close_over_call_graph(scan, direct_tier, direct_steers):
    """Worst tier and false-green risk anywhere in each function's callee subtree.

    Iterated to a fixed point rather than by DFS, because a call graph with cycles (the game's
    main loop reaches routines that call back into it) has no topological order to fold along.
    """
    tier, steers = dict(direct_tier), dict(direct_steers)
    changed = True
    while changed:
        changed = False
        for addr, f in scan.funcs.items():
            for callee in f.callees:
                if tier[callee] > tier[addr]:
                    tier[addr] = tier[callee]
                    changed = True
                if steers[callee] and not steers[addr]:
                    steers[addr] = True
                    changed = True
    return tier, steers


def witness_path(scan, tier, root, worst):
    """A shortest call chain from `root` to a function whose OWN tier is `worst` — the concrete
    reason a root's transitive tier is what it is, so the number can be acted on."""
    queue, seen = collections.deque([(root, [root])]), {root}
    while queue:
        addr, path = queue.popleft()
        if tier[addr] == worst:
            return path
        for callee in sorted(scan.funcs[addr].callees):
            if callee not in seen:
                seen.add(callee)
                queue.append((callee, path + [callee]))
    return None


def reachable_from(scan, roots):
    seen, stack = set(), list(roots)
    while stack:
        addr = stack.pop()
        if addr in seen:
            continue
        seen.add(addr)
        stack.extend(scan.funcs[addr].callees)
    return seen


def load_subsystems(path):
    rows = []
    for line in open(path):
        if line.startswith("#") or not line.strip():
            continue
        lo, hi, name = line.rstrip("\n").split("\t")
        rows.append((int(lo, 16), int(hi, 16), name))
    return rows


def subsystem_of(entry, rows):
    for lo, hi, name in rows:
        if lo <= entry < hi:
            return name
    return "unclassified"


# --- report sections, each a self-contained list of markdown lines -----------------------------

def tier_table(scan, tier_of, keys, title):
    """Function count and code bytes per tier over `keys`."""
    count, size = collections.Counter(), collections.Counter()
    for addr in keys:
        count[tier_of[addr]] += 1
        size[tier_of[addr]] += scan.funcs[addr].size
    total_n, total_b = sum(count.values()), sum(size.values())
    out = ["### %s" % title, "",
           "| tier | functions | % | bytes | % |", "|---|---:|---:|---:|---:|"]
    for t, name in enumerate(TIER_NAMES):
        if count[t]:
            out.append("| %s | %d | %.1f%% | %d | %.1f%% |"
                       % (name, count[t], 100.0 * count[t] / total_n, size[t],
                          100.0 * size[t] / total_b))
    return out + ["| **total** | **%d** | | **%d** | |" % (total_n, total_b), ""]


def roots_table(scan, roots, direct_tier, tier, steers):
    out = ["### Why each root lands where it does", "",
           "| root | transitive tier | steering T3 below it | witness path |", "|---|---|---|---|"]
    for r in roots:
        path = witness_path(scan, direct_tier, r, tier[r])
        out.append("| `%#x` %s | %s | %s | %s |"
                   % (r, scan.funcs[r].name, TIER_NAMES[tier[r]], "yes" if steers[r] else "no",
                      " -> ".join(scan.funcs[a].name for a in path) if path else "—"))
    return out + [""]


def headline_numbers(scan, tier, steers):
    runnable = [a for a in scan.funcs if tier[a] < T_HARD_REJECT]
    at_risk = [a for a in scan.funcs if steers[a]]
    total_n, total_b = len(scan.funcs), sum(f.size for f in scan.funcs.values())
    return ["### The two numbers that decide a reconstruction order", "",
            "- **Runnable end-to-end under the oracle** (no T4/T5 anywhere in the subtree): "
            "**%d/%d functions, %d/%d bytes = %.1f %%**."
            % (len(runnable), total_n, sum(scan.funcs[a].size for a in runnable), total_b,
               100.0 * sum(scan.funcs[a].size for a in runnable) / total_b),
            "- **At false-green risk** (a control-flow-steering T3 in the subtree): "
            "**%d/%d functions, %d/%d bytes = %.1f %%**."
            % (len(at_risk), total_n, sum(scan.funcs[a].size for a in at_risk), total_b,
               100.0 * sum(scan.funcs[a].size for a in at_risk) / total_b), ""]


def census_table(scan):
    """Sites per hardware block, by direction and by whether an operand scan could see them."""
    accesses = [a for f in scan.funcs.values() for a in f.accesses] + scan.unattributed
    per_block = collections.defaultdict(collections.Counter)
    for a in accesses:
        c = per_block[a.block or "off-image, no known block"]
        c["READ" if a.is_read else "WRITE"] += 1
        c[a.mode] += 1
    out = ["### Hardware site census", "",
           "| block | sites | READ | WRITE | absolute | register-indirect |",
           "|---|---:|---:|---:|---:|---:|"]
    totals = collections.Counter()
    for name in sorted(per_block, key=lambda n: -(per_block[n]["READ"] + per_block[n]["WRITE"])):
        c = per_block[name]
        out.append("| %s | %d | %d | %d | %d | %d |"
                   % (name, c["READ"] + c["WRITE"], c["READ"], c["WRITE"], c["ABS"], c["IND"]))
        totals.update(c)
    out.append("| **total** | **%d** | **%d** | **%d** | **%d** | **%d** |"
               % (totals["READ"] + totals["WRITE"], totals["READ"], totals["WRITE"],
                  totals["ABS"], totals["IND"]))
    return out + ["", "`register-indirect` is the column an operand scan cannot produce: Ghidra "
                  "resolved those through constant propagation (`lea $ff8240,a0` then "
                  "`clr.l (a0)+`).", ""]


def subsystem_table(scan, rows, direct_tier, tier, steers):
    by_sub = collections.defaultdict(list)
    for addr in scan.funcs:
        by_sub[subsystem_of(addr, rows)].append(addr)
    out = ["### Subsystem partition", "",
           "| subsystem | fns | bytes | direct worst | transitive worst | direct T0 | "
           "runnable | false-green |", "|---|---:|---:|---|---|---|---|---|"]
    for name in sorted(by_sub, key=lambda n: -sum(scan.funcs[a].size for a in by_sub[n])):
        addrs = by_sub[name]
        clean = [a for a in addrs if direct_tier[a] == T_CLEAN]
        runnable = [a for a in addrs if tier[a] < T_HARD_REJECT]
        risky = [a for a in addrs if steers[a]]
        out.append("| %s | %d | %d | %s | %s | %d / %d B | %d / %d B | %d / %d B |"
                   % (name, len(addrs), sum(scan.funcs[a].size for a in addrs),
                      TIER_NAMES[max(direct_tier[a] for a in addrs)],
                      TIER_NAMES[max(tier[a] for a in addrs)],
                      len(clean), sum(scan.funcs[a].size for a in clean),
                      len(runnable), sum(scan.funcs[a].size for a in runnable),
                      len(risky), sum(scan.funcs[a].size for a in risky)))
    return out + [""]


def hardware_functions_table(scan, excluded, direct_tier, tier):
    out = ["### Every function that touches hardware directly", "",
           "| addr | name | bytes | direct | transitive | accesses |", "|---|---|---:|---|---|---|"]
    for addr in sorted(scan.funcs):
        f = scan.funcs[addr]
        if not f.accesses and addr not in excluded:
            continue
        blocks = collections.Counter(
            "%s-%s%s" % (a.block or "off-image", "R" if a.is_read else "W", "!" if a.steers else "")
            for a in f.accesses)
        out.append("| `%#x` | %s | %d | %s | %s | %s |"
                   % (addr, f.name, f.size, TIER_NAMES[direct_tier[addr]], TIER_NAMES[tier[addr]],
                      ", ".join("%s×%d" % (k, v) for k, v in sorted(blocks.items())) or "—"))
    return out + [""]


def steering_table(scan):
    out = ["### Every hardware READ that steers a branch (the false-green surface)", "",
           "| insn | in | hw | instruction |", "|---|---|---|---|"]
    sites = 0
    for addr in sorted(scan.funcs):
        for a in scan.funcs[addr].accesses:
            if a.steers:
                sites += 1
                out.append("| `%#x` | %s | `%#x` %s | `%s` |"
                           % (a.insn, scan.funcs[addr].name, a.masked, a.block, a.text))
    fns = len({addr for addr in scan.funcs if any(a.steers for a in scan.funcs[addr].accesses)})
    return out + ["", "**%d site(s) in %d function(s).**" % (sites, fns), ""]


def stored_reads_section(scan):
    """T3-DATA reads whose value reaches a memory write: incomplete rather than falsely green,
    but the value that lands in the image is fabricated, so it is worth naming separately."""
    rows = [(a, scan.funcs[addr]) for addr in sorted(scan.funcs)
            for a in scan.funcs[addr].accesses if a.is_read and a.stored and not a.steers]
    if not rows:
        return []
    out = ["### Hardware reads whose fabricated value is STORED (T3-DATA, not falsely green)", "",
           "| insn | in | hw | instruction |", "|---|---|---|---|"]
    for a, f in rows:
        out.append("| `%#x` | %s | `%#x` %s | `%s` |" % (a.insn, f.name, a.masked, a.block, a.text))
    return out + [""]


def blind_spots_section(scan, exclusions, roots, reach):
    out = ["### What this method cannot see", "",
           "- **%d unresolved indirect call/jump site(s)**: the call graph under them is unknown, "
           "so a transitive tier is a LOWER bound wherever one appears." % len(scan.indirect)]
    for fn, insn, text in scan.indirect:
        out.append("  - `%#x` in `%s`: `%s`" % (insn, fn, text))
    orphan_bytes = sum(n for _, _, n in scan.orphans)
    orphan_span = sum(hi - lo for lo, hi, _ in scan.orphans)
    out.append("- **%d byte(s) of disassembled code in no function**, in %d run(s) spanning %d "
               "bytes of address range: not counted in any tier above."
               % (orphan_bytes, len(scan.orphans), orphan_span))
    if scan.unattributed:
        out.append("- **%d hardware access(es) in code attributed to no function**, so they are in "
                   "no tier above:" % len(scan.unattributed))
        for a in scan.unattributed:
            out.append("  - `%#x` -> `%#x` %s %s%s: `%s`"
                       % (a.insn, a.masked, a.block or "no known block",
                          "READ" if a.is_read else "WRITE", " (STEERS)" if a.steers else "", a.text))
    unknown = [a for f in scan.funcs.values() for a in f.accesses if a.block is None]
    if unknown:
        out.append("- **%d off-image access(es) that decode to NO known hardware block.** Each is "
                   "either a register Ghidra constant-propagated wrongly or a chip this map does "
                   "not list; both tier their function, so read them before trusting it:"
                   % len(unknown))
        for a in unknown:
            out.append("  - `%#x` -> `%#x`: `%s`" % (a.insn, a.masked, a.text))
    if roots:
        unreachable = [a for a in scan.funcs if a not in reach]
        out.append("- **%d function(s) (%d bytes) are unreachable in the static call graph** from "
                   "the roots — mostly the other side of the indirect sites above. They are tiered "
                   "but not rooted."
                   % (len(unreachable), sum(scan.funcs[a].size for a in unreachable)))
    for lo, hi, label in exclusions:
        out.append("- **`%#x..%#x` (%d bytes, %s)**: excluded as unreadable; no scan of any kind "
                   "covers it." % (lo, hi, hi - lo, label))
    out.append("- Code the disassembler never reached at all is invisible here — cross-check the "
               "site count against an independent linear sweep of the whole image.")
    return out + [""]


def build_report(args, scan, exclusions, excluded, extra, roots):
    direct_tier, direct_steers = direct_tiers(scan, excluded)
    tier, steers = close_over_call_graph(scan, direct_tier, direct_steers)
    reach = reachable_from(scan, roots) if roots else set(scan.funcs)

    out = ["# %s" % args.title, "",
           "Program `%s`, oracle image size `%s`, %d functions, %d call-graph edges "
           "(%s), %d hardware/off-image accesses."
           % (scan.facts.get("program", "?"), scan.facts.get("image_size", "?"), len(scan.funcs),
              sum(len(f.callees) for f in scan.funcs.values()),
              ", ".join("%d %s" % (n, k) for k, n in sorted(scan.edge_kinds.items())),
              sum(len(f.accesses) for f in scan.funcs.values()) + len(scan.unattributed))]
    if extra:
        out.append("%d site(s) folded in from --extra-hw (a stated blind spot of the scan)."
                   % len(extra))
    if args.model:
        out.append("Assumed modeled by the harness, so these accesses cost no tier: %s."
                   % ", ".join(sorted(args.model)))
    if args.stub:
        out.append("Stubbed out (treated as a harness replacement with no accesses and no "
                   "callees): %s." % ", ".join("`%s` %s" % (a, scan.funcs[int(a, 16)].name)
                                               for a in args.stub))
    out += ["**Coverage of the measurement.** The disassembler reached %s bytes, of which %s are "
            "inside a function body and therefore tiered below. Everything it never reached is "
            "outside every number in this report."
            % (scan.facts.get("disassembled_bytes", "?"), scan.facts.get("function_bytes", "?")),
            ""]

    out += tier_table(scan, direct_tier, scan.funcs, "Direct tier (what the function itself touches)")
    out += tier_table(scan, tier, scan.funcs,
                      "Transitive tier (worst tier anywhere in its callee subtree)")
    if roots:
        out += tier_table(scan, tier, reach,
                          "Transitive tier, restricted to functions reachable from %s"
                          % ", ".join("`%#x`" % r for r in roots))
        out += roots_table(scan, roots, direct_tier, tier, steers)
    out += headline_numbers(scan, tier, steers)
    out += census_table(scan)
    if args.subsystems:
        out += subsystem_table(scan, load_subsystems(args.subsystems), direct_tier, tier, steers)
    out += hardware_functions_table(scan, excluded, direct_tier, tier)
    out += steering_table(scan)
    out += stored_reads_section(scan)
    out += blind_spots_section(scan, exclusions, roots, reach)
    return out


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scan")
    ap.add_argument("--exclude", action="append", default=[], metavar="LO:HI:LABEL")
    ap.add_argument("--root", action="append", default=[], metavar="ADDR")
    ap.add_argument("--subsystems")
    ap.add_argument("--extra-hw")
    ap.add_argument("--stub", action="append", default=[], metavar="ADDR")
    ap.add_argument("--model", action="append", default=[], metavar="BLOCK:read|write")
    ap.add_argument("--title", default="Hardware portability")
    return ap.parse_args()


def main():
    check_shim_agreement()
    args = parse_args()

    known_blocks = {name for _, _, name in HW_BLOCKS}
    modeled = set()
    for spec in args.model:
        block, _, direction = spec.partition(":")
        if block not in known_blocks or direction not in ("read", "write"):
            sys.exit("--model %s: expected <block>:read|write with block in %s"
                     % (spec, ", ".join(sorted(known_blocks))))
        modeled.add((block, direction))

    scan = parse_scan(args.scan, modeled)
    # A scan with no functions in it would otherwise print a report of zeroes and exit 0 — the
    # "nothing measured reads as everything clean" failure the corpus harnesses in this workspace
    # also guard against. A truncated or failed hw_scan.sh run looks exactly like this.
    if not scan.funcs:
        sys.exit("%s contains no F records — nothing was classified. Re-run tools/hw_scan.sh; a "
                 "Ghidra run that failed still leaves a header-only TSV behind." % args.scan)

    extra = apply_extra_hw(scan, args.extra_hw, modeled) if args.extra_hw else []
    for spec in args.stub:
        stubbed = scan.funcs.get(int(spec, 16))
        if stubbed is None:
            sys.exit("--stub %s names no function in the scan" % spec)
        stubbed.accesses, stubbed.callees = [], set()
    # Roots are validated, unlike a silently-dropped one: re-bootstrapping the DB moves function
    # boundaries, and a root that stopped naming an entry would quietly shrink the "reachable"
    # table into a smaller, healthier-looking one under a heading that still claims the old root.
    roots = []
    for spec in args.root:
        addr = int(spec, 16)
        if addr not in scan.funcs:
            sys.exit("--root %s names no function in the scan — the closure would silently omit "
                     "its whole subtree" % spec)
        roots.append(addr)

    exclusions = []
    for spec in args.exclude:
        lo, hi, label = spec.split(":")
        exclusions.append((int(lo, 16), int(hi, 16), label))
    excluded = apply_exclusions(scan, exclusions)
    for spec in args.stub:                    # a stub replaces the body, unreadable or not
        excluded.pop(int(spec, 16), None)

    sys.stdout.write("\n".join(build_report(args, scan, exclusions, excluded, extra, roots)))


if __name__ == "__main__":
    main()
