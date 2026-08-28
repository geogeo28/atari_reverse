// Resolves Line-A opcodes ($aXXX) so 68000 disassembly does not stop dead at them.
//
// Ghidra's 68000 SLEIGH has no constructor for the $Axxx opcode row (on the ST those
// words are TOS Line-A graphics calls), so disassembly halts at one and everything
// reachable only past it stays undiscovered. Mechanism, symptoms and measured effect:
// docs/ghidra-pipeline.md, "Line-A opcodes"; the call table: docs/tos-os-calls.md.
//
// Contract — for every instruction whose fall-through lands on an undisassembled
// $aXXX word: define the word as data, comment it (EOL at the word for the listing,
// pre-comment at the resume address so it also reaches the decompiled C), give the
// PRECEDING instruction a fall-through override past it, disassemble from the next
// word, and re-body the host function (a body is frozen at creation, so without this
// _start still exports as its first few instructions). Looped to a fixed point,
// re-analyzing each pass when asked, since new code can hold further Line-A words.
//
// LIMITATION — the override models the Line-A call as a NO-OP, which can make the C
// positively wrong, not merely incomplete: a Line-A call destroys d0-d2/a0-a2, and
// $a000 RETURNS the Line-A variable block in a0 (font header in a1, tables in a2). So
// `lea tbl,a0 / dc.w $a000 / move.l 2(a0),d1` decompiles as a read of tbl+2 when the
// hardware reads Line-A_var_block+2. Check the comment before trusting d0-d2/a0-a2
// across a site. A site whose registers are all reloaded before use (Zynaps' single
// $a00a) is unaffected.
//
// Args: `reanalyze` — re-run auto-analysis over the changes each pass. Pass it in the
// post-analysis position so functions are created for the newly reached code.
// Run after PrgLoader (pre-analysis) AND after auto-analysis; see tools/headless.sh.
//
//@category Atari.ST
//@menupath Tools.Atari.Resolve Line-A opcodes
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.WordDataType;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class LineAResolve extends GhidraScript {

    static final int LINE_A_MASK = 0xf000;      // $aXXX = the 68000's "line A" opcode row
    static final int LINE_A_PREFIX = 0xa000;
    static final int LINE_A_LEN = 2;            // the opcode word; Line-A takes no extension words
    static final int MAX_PASSES = 64;           // fixed-point guard (each pass resolves >=1 site)
    static final int MAX_UNRESOLVED_LISTED = 32;
    static final String REANALYZE_ARG = "reanalyze";

    // TOS Line-A graphics API, indexed by the opcode's low 12 bits. Pinned against the table in
    // docs/tos-os-calls.md by tools/recreate_kit/test/test_line_a_table.py — change both together.
    static final String[] LINE_A_CALLS = {
        "Init", "Put pixel", "Get pixel", "Line", "Horizontal line", "Filled rectangle",
        "Line-by-line filled polygon", "BitBlt", "TextBlt", "Show mouse", "Hide mouse",
        "Transform mouse", "Undraw sprite", "Draw sprite", "Copy raster form", "Contour fill",
    };

    /** An instruction that falls through onto an unresolved Line-A word. */
    private static final class Site {
        final Instruction from;
        final Address at;
        final int opcode;

        Site(Instruction from, Address at, int opcode) {
            this.from = from;
            this.at = at;
            this.opcode = opcode;
        }
    }

    @Override
    public void run() throws Exception {
        boolean reanalyze = false;
        for (String arg : getScriptArgs()) {
            reanalyze |= REANALYZE_ARG.equals(arg);
        }

        int resolved = 0;
        int reBodied = 0;
        for (int pass = 0; pass < MAX_PASSES && !monitor.isCancelled(); pass++) {
            List<Site> sites = findSites();
            if (sites.isEmpty()) {
                break;
            }
            Set<Function> hosts = new LinkedHashSet<>();
            for (Site site : sites) {
                resolve(site);
                resolved++;
                println("  resolved " + site.at + "  " + label(site.opcode));
                Function host = getFunctionContaining(site.from.getMinAddress());
                if (host != null) {
                    hosts.add(host);
                }
            }
            reBodied += reBody(hosts);
            if (reanalyze) {          // inside the loop: re-analysis can expose further Line-A words
                analyzeChanges(currentProgram);
            }
        }
        println("resolved " + resolved + " Line-A opcode sites, re-bodied " + reBodied + " functions");
        reportUnresolved();
    }

    // Collected in full before any listing edits: resolving a site invalidates the iterator.
    private List<Site> findSites() throws Exception {
        List<Site> sites = new ArrayList<>();
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction insn = it.next();
            Address next = insn.getFallThrough();
            if (next == null || getInstructionAt(next) != null || !isUndefined(next)) {
                continue;
            }
            int word = readWord(next);
            if ((word & LINE_A_MASK) == LINE_A_PREFIX) {
                sites.add(new Site(insn, next, word));
            }
        }
        return sites;
    }

    private void resolve(Site site) throws Exception {
        Address resume = site.at.add(LINE_A_LEN);
        clearListing(site.at, resume.subtract(1));   // the 2 opcode bytes may carry a defined unit
        createData(site.at, WordDataType.dataType);
        setEOLComment(site.at, label(site.opcode) + " -- execution continues below (fall-through override)");
        // Pre-comment, not EOL: the decompiler's COMMENTEOL option is off by default, and it is
        // placed at `resume` because the skipped word itself is no longer inside the function body.
        setPreComment(resume, label(site.opcode) + " executed at " + site.at
                + " -- skipped by a fall-through override: no call and no register clobber appears"
                + " here (Line-A destroys d0-d2/a0-a2; $a000 returns a0/a1/a2)");
        site.from.setFallThrough(resume);            // flow (and the decompiler) skips the opcode word
        disassemble(resume);
    }

    // A frozen function body must be recomputed for the code past the site to belong to it.
    private int reBody(Set<Function> hosts) throws Exception {
        int fixed = 0;
        for (Function func : hosts) {
            if (CreateFunctionCmd.fixupFunctionBody(currentProgram, func, monitor)) {
                fixed++;
            } else {
                printerr("WARNING: could not re-body " + func.getName() + " @ " + func.getEntryPoint()
                        + " -- flow past its Line-A site probably runs into another function's entry");
            }
        }
        return fixed;
    }

    // Self-report the known gap: only fall-through sites are resolved, so a Line-A word that a
    // branch or call jumps straight to is left alone (disassembly of that target failed silently).
    // An incoming FLOW reference is what separates such a site from the many $a00x words that are
    // simply data — on JOUST.PRG a value-only sweep flags 4 words, all of them sprite bitmap rows.
    private void reportUnresolved() throws Exception {
        List<Address> left = new ArrayList<>();
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            if (!block.isInitialized() || !block.isExecute()) {
                continue;
            }
            Address addr = block.getStart();
            while (addr.compareTo(block.getEnd()) < 0 && !monitor.isCancelled()) {
                if (isUndefined(addr) && isDocumentedCall(readWord(addr)) && hasFlowReferenceTo(addr)) {
                    left.add(addr);
                }
                addr = addr.add(LINE_A_LEN);
            }
        }
        if (left.isEmpty()) {
            return;
        }
        println("unresolved Line-A words reached by a branch/call, NOT handled: " + left.size());
        for (int i = 0; i < left.size() && i < MAX_UNRESOLVED_LISTED; i++) {
            println("  " + left.get(i) + "  " + label(readWord(left.get(i))));
        }
    }

    private boolean isDocumentedCall(int word) {
        return (word & LINE_A_MASK) == LINE_A_PREFIX && (word & ~LINE_A_MASK) < LINE_A_CALLS.length;
    }

    private boolean hasFlowReferenceTo(Address addr) {
        for (Reference ref : getReferencesTo(addr)) {
            if (ref.getReferenceType().isFlow()) {
                return true;
            }
        }
        return false;
    }

    private boolean isUndefined(Address addr) {
        Data data = getDataAt(addr);
        return data == null || !data.isDefined();
    }

    // -1 for unreadable/uninitialized memory: never equal to a Line-A word.
    private int readWord(Address addr) {
        try {
            return getShort(addr) & 0xffff;
        } catch (Exception e) {
            return -1;
        }
    }

    private String label(int opcode) {
        int call = opcode & ~LINE_A_MASK;
        String name = call < LINE_A_CALLS.length ? LINE_A_CALLS[call] : "not a documented call";
        return String.format("Line-A $%04x (%s)", opcode, name);
    }
}
