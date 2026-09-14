// Resolves the GEM Line-F call opcodes ($fXXX) so 68000 disassembly does not stop dead
// at them -- the AES/desktop counterpart of LineAResolve.
//
// MECHANISM. GEM in ROM does not call its own routines with `jsr`. The AES and the
// desktop are compiled so that a subroutine call is ONE WORD in the $fXXX opcode row,
// which the 68000 takes as the Line-F exception (vector $2c). TOS installs a ~100-byte
// handler there (TOS 1.02 US: copied from $fee8c2 into a Malloc'd buffer at AES init),
// and that handler decodes the word it faulted on:
//
//   even word  ($f2b4)  -> CALL: target = tbl[(op & $0fff) / 4], return address = the
//                          word after the opcode. One word instead of six.
//   odd word   ($f001)  -> RETURN: `unlk a6; rts`; a non-zero odd value additionally
//                          restores registers with a movem mask of (op & $0ffe) * 4.
//
// `tbl` is a longword table of every routine reachable this way (TOS 1.02 US: 658
// entries at $fee900, i.e. opcodes $f000..$fa44). This script finds it by the handler's
// own dispatch signature -- `andi.w #$0fff,d1 / movea.l #tbl,a0 / movea.l (a0,d1.w),a0 /
// jmp (a0)` -- so nothing is hardcoded to one ROM. No table base is accepted as an argument:
// the signature is the whole contract, and an image without it gets a clear message.
//
// Ghidra's 68000 SLEIGH has no constructor for $fXXX, so without this script every AES
// and desktop function truncates at its first call and most of them are never reached
// at all.
//
// CONTRACT (the same shape as LineAResolve, see docs/ghidra-pipeline.md "Line-A
// opcodes"): for every instruction whose fall-through lands on an undisassembled $fXXX
// word -- define the word as data, comment it (EOL at the word, pre-comment at the
// resume address so it reaches the decompiled C), record a CALL reference to the
// resolved target, give the PRECEDING instruction a fall-through override past the run
// of opcode words, disassemble from the word after it, and re-body the host function.
// A run of consecutive $fXXX words is handled in one step, because after the first is
// turned into data no instruction falls through onto the second.
//
// LIMITATIONS, both of which make the exported C WRONG rather than merely incomplete:
//   * a resolved call is modelled as a NO-OP. The callee's return value (d0) and its
//     register clobbers are invisible, so an expression reading d0 after a site
//     decompiles from whatever last wrote d0 BEFORE it. Read the comment at the site.
//   * at a RETURN word the flow simply ends (no fall-through override is set), so the
//     function's body stops there -- correct for $f001, but a `movem` restore mask is
//     not modelled either.
//
// Words a branch or call JUMPS TO are not resolved at all (only fall-through sites are);
// the run ends by reporting how many of those are left, as LineAResolve does.
//
// Args: `reanalyze` -- re-run auto-analysis over the changes each pass (use in the
// post-analysis position).
//
//@category Atari.ST
//@menupath Tools.Atari.Resolve GEM Line-F calls
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.WordDataType;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.RefType;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.SourceType;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class LineFResolve extends GhidraScript {

    static final int LINE_F_ROW = 0xf000;           // $fXXX = the 68000's "line F" opcode row
    static final int LINE_F_LEN = 2;                // the opcode word; no extension words
    static final int CALL_INDEX_MASK = 0x0fff;      // byte offset into the call table
    static final int RETURN_BIT = 0x0001;           // set = return, clear = call
    static final int MOVEM_MASK_SHIFT = 2;          // handler: lsl.w #2 on (op & $0ffe)
    static final int TABLE_STRIDE = 4;              // the call table holds longword addresses
    static final int MAX_PASSES = 64;               // fixed-point guard
    static final int MAX_UNRESOLVED_LISTED = 32;
    static final String REANALYZE_ARG = "reanalyze";

    // The handler's dispatch, word by word: andi.w #$0fff,d1 / movea.l #tbl,a0 /
    // movea.l (a0,d1.w),a0 / jmp (a0). The table base is the longword inside it.
    static final int[] DISPATCH_PREFIX = {0x0241, 0x0fff, 0x207c};
    static final int[] DISPATCH_SUFFIX = {0x2070, 0x1000, 0x4ed0};
    static final int DISPATCH_BASE_OFFSET = DISPATCH_PREFIX.length * 2;
    static final int DISPATCH_BASE_LEN = 4;         // the `movea.l #tbl,a0` immediate operand

    private long tableBase;
    private int tableEntries;

    /** An instruction that falls through onto an unresolved Line-F word. */
    private static final class Site {
        final Instruction from;
        final Address at;

        Site(Instruction from, Address at) {
            this.from = from;
            this.at = at;
        }
    }

    @Override
    public void run() throws Exception {
        boolean reanalyze = false;
        for (String arg : getScriptArgs()) {
            reanalyze |= REANALYZE_ARG.equals(arg);
        }
        tableBase = findCallTable();
        if (tableBase == 0) {
            println("LineFResolve: no Line-F dispatch handler in this image -- nothing to do");
            return;
        }
        tableEntries = countEntries(tableBase);
        if (tableEntries == 0) {
            println(String.format("LineFResolve: no readable call table at 0x%x -- nothing to do",
                    tableBase));
            return;
        }
        println(String.format("Line-F call table: %d entries at 0x%x (opcodes $f000..$f%03x)",
                tableEntries, tableBase, (tableEntries - 1) * TABLE_STRIDE));

        int resolved = 0;
        int reBodied = 0;
        boolean converged = false;
        for (int pass = 0; pass < MAX_PASSES && !monitor.isCancelled(); pass++) {
            List<Site> sites = findSites();
            if (sites.isEmpty()) {
                converged = true;
                break;
            }
            Set<Function> hosts = new LinkedHashSet<>();
            for (Site site : sites) {
                resolved += resolve(site);
                Function host = getFunctionContaining(site.from.getMinAddress());
                if (host != null) {
                    hosts.add(host);
                }
            }
            reBodied += reBody(hosts);
            if (reanalyze) {      // inside the loop: re-analysis can expose further Line-F words
                analyzeChanges(currentProgram);
            }
        }
        if (!converged && !monitor.isCancelled()) {
            printerr("LineFResolve: still finding Line-F sites after " + MAX_PASSES
                    + " passes -- the resolve loop did not converge; run the script again");
        }
        println("resolved " + resolved + " Line-F opcode words, re-bodied " + reBodied + " functions");
        reportUnresolved();
    }

    /** Scan executable memory for the Line-F handler's dispatch and read its table base. */
    private long findCallTable() throws Exception {
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            if (!block.isInitialized() || !block.isExecute()) {
                continue;
            }
            Address addr = block.getStart();
            Address last = block.getEnd().subtract(
                    DISPATCH_BASE_OFFSET + DISPATCH_BASE_LEN + DISPATCH_SUFFIX.length * 2);
            while (addr.compareTo(last) < 0 && !monitor.isCancelled()) {
                if (matches(addr)) {
                    return getInt(addr.add(DISPATCH_BASE_OFFSET)) & 0xffffffffL;
                }
                addr = addr.add(2);
            }
        }
        return 0;
    }

    private boolean matches(Address addr) {
        for (int i = 0; i < DISPATCH_PREFIX.length; i++) {
            if (readWord(addr.add(2L * i)) != DISPATCH_PREFIX[i]) {
                return false;
            }
        }
        Address suffix = addr.add(DISPATCH_BASE_OFFSET + DISPATCH_BASE_LEN);
        for (int i = 0; i < DISPATCH_SUFFIX.length; i++) {
            if (readWord(suffix.add(2L * i)) != DISPATCH_SUFFIX[i]) {
                return false;
            }
        }
        return true;
    }

    /** The table runs until the first longword that is not an address inside this image. */
    private int countEntries(long base) throws Exception {
        MemoryBlock code = getMemoryBlock(toAddr(base));
        if (code == null) {
            println(String.format("LineFResolve: the dispatch names a table at 0x%x, which is in"
                    + " no memory block", base));
            return 0;
        }
        int n = 0;
        while (true) {
            Address at = toAddr(base + (long) TABLE_STRIDE * n);
            if (!code.contains(at)) {
                break;
            }
            long target = getInt(at) & 0xffffffffL;
            MemoryBlock block = getMemoryBlock(toAddr(target));
            if (block == null || !block.isExecute()) {
                break;
            }
            n++;
        }
        return n;
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
            if (isLineF(readWord(next))) {
                sites.add(new Site(insn, next));
            }
        }
        return sites;
    }

    /**
     * Resolve the whole run of Line-F words starting at the site. Returns how many words it
     * consumed. Execution resumes after the run only if the run holds no RETURN word.
     */
    private int resolve(Site site) throws Exception {
        Address at = site.at;
        Address returnWord = null;
        int words = 0;
        while (isLineF(readWord(at)) && isUndefined(at)) {
            int opcode = readWord(at);
            defineWord(at, opcode);
            println("  resolved " + at + "  " + label(opcode));
            words++;
            if ((opcode & RETURN_BIT) != 0) {
                returnWord = at;
                break;
            }
            at = at.add(LINE_F_LEN);
        }
        if (words == 0) {
            return 0;
        }
        int calls = returnWord != null ? words - 1 : words;
        if (returnWord != null) {
            // On the return word itself, not on the run's first word: the words before it are
            // calls, and this comment is about where the function stops.
            setPreComment(returnWord, "Line-F RETURN here: the function ends at this word, and"
                    + " the flow past it is NOT modelled (no fall-through override is set)");
            if (calls > 0) {
                setPreComment(site.at, callNote(calls, site.at));
            }
            return words;
        }
        // Pre-comment at the RESUME address, not on the skipped words: the words are data
        // outside the function body, so only a comment here reaches the decompiled C.
        setPreComment(at, callNote(calls, site.at)
                + ". Execution resumes here, past a fall-through override");
        site.from.setFallThrough(at);
        disassemble(at);
        return words;
    }

    private String callNote(int calls, Address at) {
        return calls + " Line-F call word(s) execute at " + at
                + " -- they are data in the listing, so no call appears and the callee's result"
                + " (d0) and register clobbers are invisible to the decompiler";
    }

    private void defineWord(Address at, int opcode) throws Exception {
        clearListing(at, at.add(LINE_F_LEN - 1));
        createData(at, WordDataType.dataType);
        setEOLComment(at, label(opcode));
        long target = callTarget(opcode);
        if (target != 0) {
            currentProgram.getReferenceManager().addMemoryReference(
                    at, toAddr(target), RefType.UNCONDITIONAL_CALL, SourceType.ANALYSIS, 0);
        }
    }

    /** The routine an even Line-F word calls, or 0 for a return word / an out-of-range index. */
    private long callTarget(int opcode) throws Exception {
        if ((opcode & RETURN_BIT) != 0) {
            return 0;
        }
        int index = opcode & CALL_INDEX_MASK;         // a BYTE offset, so the last valid one is
        if (!isInTable(index)) {                      // (tableEntries - 1) * TABLE_STRIDE
            return 0;
        }
        return getInt(toAddr(tableBase + index)) & 0xffffffffL;
    }

    // A frozen function body must be recomputed for the code past the site to belong to it.
    private int reBody(Set<Function> hosts) throws Exception {
        int fixed = 0;
        for (Function func : hosts) {
            if (CreateFunctionCmd.fixupFunctionBody(currentProgram, func, monitor)) {
                fixed++;
            } else {
                printerr("WARNING: could not re-body " + func.getName() + " @ " + func.getEntryPoint()
                        + " -- flow past its Line-F site probably runs into another function's entry");
            }
        }
        return fixed;
    }

    /**
     * Line-F words this script could have resolved but never saw, because a branch or a call
     * jumps straight to them instead of an instruction falling through onto them.
     */
    private void reportUnresolved() throws Exception {
        List<Address> left = new ArrayList<>();
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            if (!block.isInitialized() || !block.isExecute()) {
                continue;
            }
            Address addr = block.getStart();
            while (addr.compareTo(block.getEnd()) < 0 && !monitor.isCancelled()) {
                if (isUndefined(addr) && isResolvable(readWord(addr)) && hasFlowReferenceTo(addr)) {
                    left.add(addr);
                }
                addr = addr.add(LINE_F_LEN);
            }
        }
        if (left.isEmpty()) {
            return;
        }
        println("unresolved Line-F words reached by a branch/call, NOT handled: " + left.size());
        for (int i = 0; i < left.size() && i < MAX_UNRESOLVED_LISTED; i++) {
            println("  " + left.get(i) + "  " + label(readWord(left.get(i))));
        }
    }

    /** A Line-F word this script knows how to decode: a return, or a call inside the table. */
    private boolean isResolvable(int word) {
        return isLineF(word)
                && ((word & RETURN_BIT) != 0 || isInTable(word & CALL_INDEX_MASK));
    }

    private boolean hasFlowReferenceTo(Address addr) {
        for (Reference ref : getReferencesTo(addr)) {
            if (ref.getReferenceType().isFlow()) {
                return true;
            }
        }
        return false;
    }

    private boolean isLineF(int word) {
        return (word & LINE_F_ROW) == LINE_F_ROW;
    }

    /** True if a whole longword entry at this BYTE offset lies inside the call table. */
    private boolean isInTable(int index) {
        return index + TABLE_STRIDE <= tableEntries * TABLE_STRIDE;
    }

    private boolean isUndefined(Address addr) {
        Data data = getDataAt(addr);
        return data == null || !data.isDefined();
    }

    // -1 for unreadable/uninitialized memory: never equal to a Line-F word.
    private int readWord(Address addr) {
        try {
            return getShort(addr) & 0xffff;
        } catch (Exception e) {
            return -1;
        }
    }

    private String label(int opcode) {
        if ((opcode & RETURN_BIT) != 0) {
            int mask = (opcode & ~RETURN_BIT & CALL_INDEX_MASK) << MOVEM_MASK_SHIFT;
            return mask == 0
                    ? String.format("Line-F $%04x (return: unlk a6; rts)", opcode)
                    : String.format("Line-F $%04x (return: movem mask 0x%04x; unlk a6; rts)",
                            opcode, mask);
        }
        long target = 0;
        try {
            target = callTarget(opcode);
        } catch (Exception e) {
            target = 0;
        }
        return target == 0
                ? String.format("Line-F $%04x (call, index outside the table)", opcode)
                : String.format("Line-F $%04x (call %s)", opcode, toAddr(target));
    }
}
