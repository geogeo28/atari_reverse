// Dumps everything a "how much of this game can a memory-only differential see?" measurement
// needs, straight out of Ghidra's own models — function bodies, the call graph, and every
// hardware/off-image memory access with its direction and whether it steers a branch.
//
// Game-agnostic: it knows the Atari ST I/O map (below) and nothing about any particular program.
// Drive it with tools/hw_scan.sh; post-process the TSV with tools/hw_portability.py.
//
// WHY GHIDRA'S REFERENCE MODEL AND NOT A LINEAR SWEEP (docs/m68k-disassembly.md): a sweep
// desyncs on data and silently drops the instructions after it. Ghidra's references also
// already resolve `lea $ff8800,a0` + `move.b d0,(a0)` to $ff8800 by constant propagation, which
// is the register-indirect idiom a hand-written-assembly game uses and an operand scan misses.
//
// Output is TSV, one record per line, first field = record type:
//   P  key             value                        program-level facts. functions /
//                                                   function_bytes / disassembled_bytes are
//                                                   the denominators the tiers are out of.
//   F  entry  bytes  body_end  name        one per function. bytes = body address count;
//                                          body_end = one past its highest address, which is
//                                          what an --exclude range must be tested against
//                                          (a Ghidra body can be non-contiguous)
//   E  from   to       kind                         call-graph edge. CALL / JUMP (a tail call
//                                                   to a function ENTRY) / JUMPIN (a branch into
//                                                   the MIDDLE of another function — this game's
//                                                   boot chain is built out of those)
//   I  fn     insn     text                         unresolved indirect call/jump (a blind spot).
//                                                   An indirect site lands here only when nothing
//                                                   resolved it: a fixed-base one that Ghidra DID
//                                                   resolve (`lea $17adc,a1 / jsr (a1)`, and
//                                                   `jsr d16(a1)` via effectiveAddresses() below)
//                                                   is an E edge like any other. Every call/jump
//                                                   instruction is in exactly one of the two
//                                                   ledgers — a site in neither is a scan DEFECT.
//   H  fn insn hwaddr size dir mode steer stored text   one hardware/off-image access
//   O  start  end  bytes                             a run of code outside any function.
//                                                    start..end is the address SPAN (it can
//                                                    enclose undefined data); bytes is the
//                                                    instruction bytes actually in it
// size  = bytes transferred (1/2/4), or ? when the pcode did not name one. It decides tier: the
//         oracle models ONLY the byte protocol on the PSG's two canonical ports.
// dir   = READ | WRITE
// mode  = ABS (the operand names the address) | IND (Ghidra resolved it through a register)
// steer = STEER   a conditional branch consumed a value derived from this READ
//         DEAD    the read value was fully overwritten before any branch used it
//         WINDOW  still live when the taint walk gave up (undecided — read the code)
//         -       writes, which cannot steer anything
// stored = STORED if a value derived from the READ reached a memory write, else "-"
//
//@category Atari.ST
//@menupath Tools.Atari.Hardware portability scan
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.pcode.Varnode;
import ghidra.program.model.symbol.FlowType;
import ghidra.program.model.symbol.Reference;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;

public class HwPortabilityScan extends GhidraScript {

    /** The 68000 has a 24-bit address bus, so $ffff8800 and $ff8800 reach the same chip. This is
     *  the same mask the differential oracle applies (tools/recreate_kit/oracle/shim.c). */
    private static final long BUS_ADDR_MASK = 0xffffffL;
    /** Default flat-image size of the oracle; anything at or above it is off-image to the shim. */
    private static final long DEFAULT_IMAGE_SIZE = 0x100000L;
    /** How far the taint walk follows a READ before giving up. */
    private static final int STEER_WINDOW_INSNS = 48;

    private long imageSize = DEFAULT_IMAGE_SIZE;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String out = args.length > 0 ? args[0] : "hw_scan.tsv";
        if (args.length > 1) {
            imageSize = Long.decode(args[1]);
        }

        try (PrintWriter w = new PrintWriter(out)) {
            w.println("# HwPortabilityScan — see the header of tools/ghidra_scripts/"
                    + "HwPortabilityScan.java for the record format");
            emit(w, "P", "program", currentProgram.getName());
            emit(w, "P", "image_size", String.format("0x%x", imageSize));
            emit(w, "P", "min_addr", currentProgram.getMinAddress().toString());
            emit(w, "P", "max_addr", currentProgram.getMaxAddress().toString());

            // Union of every function body, kept as an AddressSet (a list of ranges) rather than
            // one boxed address per byte: this is the denominator the tier totals are out of.
            AddressSet covered = new AddressSet();
            int nFn = 0;
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                AddressSetView body = f.getBody();
                if (f.isThunk() && body.getNumAddresses() == 0) {
                    continue;
                }
                nFn++;
                emit(w, "F", hex(f.getEntryPoint()), Long.toString(body.getNumAddresses()),
                        String.format("0x%x", body.getMaxAddress().getOffset() + 1), f.getName());
                covered.add(body);
            }
            emit(w, "P", "functions", Integer.toString(nFn));
            emit(w, "P", "function_bytes", Long.toString(covered.getNumAddresses()));

            // Walk EVERY disassembled instruction, not just the ones inside a function: code
            // Ghidra left unattributed still touches hardware, and a per-function walk would
            // silently drop it. Unattributed instructions are reported under the function id "-"
            // and their extent is summarised as O records, because they are a hole in the totals.
            long runStart = -1, prev = -1, insnBytes = 0, runBytes = 0;
            InstructionIterator it = currentProgram.getListing().getInstructions(true);
            while (it.hasNext()) {
                Instruction in = it.next();
                insnBytes += in.getLength();
                Function f = getFunctionContaining(in.getMinAddress());
                String fn = f == null ? "-" : hex(f.getEntryPoint());
                emitTransfers(w, f, in, fn);
                emitHardware(w, f, in, fn);

                if (f != null) {
                    if (runStart >= 0) {
                        emit(w, "O", String.format("0x%x", runStart), String.format("0x%x", prev),
                                Long.toString(runBytes));
                        runStart = -1;
                    }
                    continue;
                }
                if (runStart < 0) {
                    runStart = in.getMinAddress().getOffset();
                    runBytes = 0;
                }
                runBytes += in.getLength();
                prev = in.getMaxAddress().getOffset() + 1;
            }
            if (runStart >= 0) {
                emit(w, "O", String.format("0x%x", runStart), String.format("0x%x", prev),
                        Long.toString(runBytes));
            }
            emit(w, "P", "disassembled_bytes", Long.toString(insnBytes));
        }
        println("HwPortabilityScan -> " + out);
    }

    /** A tail-call `jmp other_function` is an edge too, and an unresolved indirect one is a hole.
     *  No call/jump instruction may leave here having emitted NOTHING: an indirect site whose
     *  targets are unknown — or known only as addresses inside no function — is the `I` ledger's
     *  whole purpose, and a silent drop is what made wonderboy's `jsr 56(a1)` at $bca2 invisible. */
    private void emitTransfers(PrintWriter w, Function f, Instruction in, String fn) {
        FlowType flow = in.getFlowType();
        if (!flow.isJump() && !flow.isCall()) {
            return;
        }
        boolean emitted = false;
        for (Address t : transferTargets(in, flow)) {
            if (f != null && f.getBody().contains(t)) {
                emitted = true;
                continue;                          // an internal branch is not a call-graph edge
            }
            Function target = getFunctionAt(t);
            String kind = flow.isCall() ? "CALL" : "JUMP";
            if (target == null) {
                target = getFunctionContaining(t);   // `bra.w` into the middle of another routine
                kind = "JUMPIN";                     // is still an edge; dropping it would make a
            }                                        // transitive tier silently too optimistic
            if (target != null && (f == null || !target.getEntryPoint().equals(f.getEntryPoint()))) {
                emit(w, "E", fn, hex(target.getEntryPoint()), kind);
                emitted = true;
            }
        }
        if (!emitted && flow.isComputed()) {
            emit(w, "I", fn, hex(in.getMinAddress()), in.toString());
        }
    }

    /** Where this transfer can go. Ghidra's own flow list, EXCEPT for the instructions whose
     *  68000 semantics it models one dereference too deep.
     *
     *  68000.sinc gives `(d16,An)` and the indexed modes as memory operands
     *  (`addrRegD16: ... export *[ram]:4 tmp`) and then spells `jsr`/`jmp` as `call [operand]` /
     *  `goto [operand]` — so the pcode LOADs the four bytes AT the effective address and calls
     *  THOSE, while a real 68000 transfers control TO the effective address and reads nothing.
     *  When constant propagation then resolves such a site it records a flow to the instruction
     *  bytes it found: wonderboy's `lea $17adc.l,a1 / jsr 56(a1)` resolved to `0x48e7fffe`, which
     *  is the `movem.l #$fffe,-(a7)` sitting at the real target $17b14. That target is in no
     *  function, so the edge loop dropped it and the site appeared in neither ledger.
     *
     *  The address the pcode LOADs from IS the effective address, and the propagator records it as
     *  the instruction's READ data reference — so for these, the read references are the targets. */
    private List<Address> transferTargets(Instruction in, FlowType flow) {
        if (flow.isComputed() && transfersThroughMemory(in)) {
            return effectiveAddresses(in);
        }
        return Arrays.asList(in.getFlows());
    }

    /** True when the pcode reaches its indirect target through a LOAD — the modelling above. */
    private boolean transfersThroughMemory(Instruction in) {
        Varnode indirectTarget = null;
        for (PcodeOp op : in.getPcode()) {
            if (op.getOpcode() == PcodeOp.CALLIND || op.getOpcode() == PcodeOp.BRANCHIND) {
                indirectTarget = op.getInput(0);
            }
        }
        if (indirectTarget == null) {
            return false;
        }
        for (PcodeOp op : in.getPcode()) {
            if (op.getOpcode() == PcodeOp.LOAD && indirectTarget.equals(op.getOutput())) {
                return true;
            }
        }
        return false;
    }

    /** The addresses constant propagation resolved the (phantom) target LOAD to. Empty when it
     *  resolved nothing — which is an honest `I` row, not a dropped site. */
    private List<Address> effectiveAddresses(Instruction in) {
        List<Address> targets = new ArrayList<>();
        for (Reference r : in.getReferencesFrom()) {
            if (r.getReferenceType().isData() && r.getReferenceType().isRead()) {
                targets.add(r.getToAddress());
            }
        }
        return targets;
    }

    /** Every memory reference out of this instruction that leaves the oracle's flat image. */
    private void emitHardware(PrintWriter w, Function f, Instruction in, String fn) {
        for (Reference r : in.getReferencesFrom()) {
            if (!r.getReferenceType().isData()) {
                continue;
            }
            boolean read = r.getReferenceType().isRead();
            boolean write = r.getReferenceType().isWrite();
            if (!read && !write) {
                continue;                          // a plain DATA ref is an address taken, not an access
            }
            long target = r.getToAddress().getOffset();
            if (target < 0) {
                continue;                          // Ghidra propagated an unknown SP/An to a
            }                                      // negative offset — a stack access, not hardware
            // Compare the RAW address against the image, exactly as the shim's bounds checks do.
            // Masking first would call an address like $01000400 in-image because its low 24 bits
            // are, while the oracle would see it above g_size and drop the access.
            if (target < imageSize) {
                continue;                          // inside the image: the differential sees it
            }
            String mode = operandNamesAddress(in, r.getOperandIndex()) ? "ABS" : "IND";
            String size = accessSize(in, target);
            // A read-modify-write (`bclr #6,$fffa11`, the standard MFP acknowledge) is ONE Ghidra
            // reference typed READ_WRITE, and it is two accesses to the oracle: a read it answers
            // 0 and a write it drops. Emitting only the first half would price the write at zero.
            if (read) {
                String[] verdict = classifyRead(f, in, target);
                emit(w, "H", fn, hex(in.getMinAddress()), String.format("0x%x", target), size,
                        "READ", mode, verdict[0], verdict[1], in.toString());
            }
            if (write) {
                emit(w, "H", fn, hex(in.getMinAddress()), String.format("0x%x", target), size,
                        "WRITE", mode, "-", "-", in.toString());
            }
        }
    }

    /** Bytes this instruction moves to/from `target`, read off the pcode rather than the mnemonic
     *  so an aliased or indirect form is sized the same way. "?" when no pcode op names it. */
    private String accessSize(Instruction in, long target) {
        long masked = target & BUS_ADDR_MASK;
        for (PcodeOp op : in.getPcode()) {
            if (op.getOpcode() == PcodeOp.LOAD && op.getOutput() != null) {
                return Integer.toString(op.getOutput().getSize());
            }
            if (op.getOpcode() == PcodeOp.STORE && op.getNumInputs() > 2) {
                return Integer.toString(op.getInput(2).getSize());
            }
            for (Varnode v : op.getInputs()) {
                if (v.isAddress() && (v.getOffset() & BUS_ADDR_MASK) == masked) {
                    return Integer.toString(v.getSize());
                }
            }
            Varnode outVn = op.getOutput();
            if (outVn != null && outVn.isAddress()
                    && (outVn.getOffset() & BUS_ADDR_MASK) == masked) {
                return Integer.toString(outVn.getSize());
            }
        }
        return "?";
    }

    /** True when the operand spells the address out (abs.w/abs.l), false when Ghidra had to
     *  constant-propagate a register to reach it — the case a raw operand scan cannot see. */
    private boolean operandNamesAddress(Instruction in, int opIndex) {
        if (opIndex < 0 || opIndex >= in.getNumOperands()) {
            return false;
        }
        for (Object o : in.getOpObjects(opIndex)) {
            if (o instanceof Address) {
                return true;
            }
        }
        return false;
    }

    // --- does a hardware READ steer control flow? -------------------------------------------
    // The oracle answers every non-PSG off-image read with 0, on BOTH sides of a differential, so
    // a read whose value only lands in memory is merely incomplete, while a read a branch depends
    // on makes the whole function FALSELY GREEN. Telling the two apart needs dataflow, not counting.
    //
    // Taint the value the read produced, propagate it through pcode along the fall-through path
    // (following unconditional jumps that stay inside the function), and see which consumes it
    // first: a conditional branch, a memory write, or an overwrite that kills it.

    /** Returns {steer verdict, stored verdict} for the read of `hwAddr` made by `in`. */
    private String[] classifyRead(Function f, Instruction in, long hwAddr) {
        List<long[]> taint = new ArrayList<>();
        boolean stored = false;
        Instruction cur = in;
        boolean seed = true;
        for (int step = 0; step < STEER_WINDOW_INSNS && cur != null; step++) {
            for (PcodeOp op : cur.getPcode()) {
                boolean tainted = seed && opReadsAddress(op, hwAddr);
                for (Varnode v : op.getInputs()) {
                    if (isTainted(taint, v)) {
                        tainted = true;
                    }
                }
                if (op.getOpcode() == PcodeOp.CBRANCH && op.getNumInputs() > 1
                        && isTainted(taint, op.getInput(1))) {
                    return new String[] { "STEER", stored ? "STORED" : "-" };
                }
                // "the value reached memory" covers BOTH pcode shapes: a STORE (register-
                // indirect) and a direct write to a ram-space varnode (absolute addressing, which
                // sleigh folds into the output rather than emitting a STORE).
                if (tainted && (op.getOpcode() == PcodeOp.STORE
                                || (op.getOutput() != null && op.getOutput().isAddress()))) {
                    stored = true;
                }
                Varnode outVn = op.getOutput();
                if (outVn != null) {
                    if (tainted) {
                        addTaint(taint, outVn);
                    } else {
                        killTaint(taint, outVn);
                    }
                }
            }
            seed = false;
            if (taint.isEmpty()) {
                return new String[] { "DEAD", stored ? "STORED" : "-" };
            }
            cur = nextInstruction(f, cur);
        }
        return new String[] { "WINDOW", stored ? "STORED" : "-" };
    }

    /** Where the taint walk goes next: fall-through, or an unconditional jump staying inside `f`.
     *  A CALL ends the walk: this game is hand-written assembly with no register-save convention
     *  to lean on, so stepping over a `bsr` would carry the callee's clobbered registers forward
     *  and manufacture STEER verdicts. Stopping yields WINDOW — "undecided, read it" — instead. */
    private Instruction nextInstruction(Function f, Instruction in) {
        FlowType flow = in.getFlowType();
        if (flow.isTerminal() || flow.isCall()) {
            return null;
        }
        if (flow.isJump() && !flow.isConditional() && !flow.isComputed()) {
            Address[] flows = in.getFlows();
            if (flows.length == 1 && inBody(f, flows[0])) {
                return getInstructionAt(flows[0]);
            }
            return null;
        }
        Address fall = in.getFallThrough();
        return fall == null || !inBody(f, fall) ? null : getInstructionAt(fall);
    }

    /** Stay inside the enclosing function; unattributed code has no body to stay inside. */
    private boolean inBody(Function f, Address a) {
        return f == null ? getInstructionAt(a) != null : f.getBody().contains(a);
    }

    /** Does this pcode op pull the hardware value in — either as a direct ram varnode (absolute
     *  addressing) or as a LOAD (register-indirect)? */
    private boolean opReadsAddress(PcodeOp op, long hwAddr) {
        if (op.getOpcode() == PcodeOp.LOAD) {
            return true;                            // the only LOAD in an instruction we already
        }                                           // know reaches hwAddr
        for (Varnode v : op.getInputs()) {
            if (v.isAddress() && (v.getOffset() & BUS_ADDR_MASK) == (hwAddr & BUS_ADDR_MASK)) {
                return true;
            }
        }
        return false;
    }

    // Taint is a list of {spaceId, start, endExclusive} byte ranges, so a sub-register (D0b) and
    // its parent (D0) taint each other without a register-hierarchy walk.
    private boolean isTainted(List<long[]> taint, Varnode v) {
        if (v == null || v.isConstant()) {
            return false;
        }
        long space = v.getAddress().getAddressSpace().getSpaceID();
        long lo = v.getOffset(), hi = lo + v.getSize();
        for (long[] t : taint) {
            if (t[0] == space && lo < t[2] && t[1] < hi) {
                return true;
            }
        }
        return false;
    }

    private void addTaint(List<long[]> taint, Varnode v) {
        if (v.isConstant()) {
            return;
        }
        killTaint(taint, v);
        taint.add(new long[] { v.getAddress().getAddressSpace().getSpaceID(), v.getOffset(),
                               v.getOffset() + v.getSize() });
    }

    /** Subtract [v, v+size) from the taint: a PARTIAL overwrite (`move.b #x,d0` over a word that
     *  came from hardware) must clear only the bytes it wrote and leave the rest tainted. Removing
     *  only wholly-covered intervals leaves the written bytes tainted and fabricates a STEER on the
     *  next `tst.b`; removing any overlapping interval would lose the bytes still holding the
     *  hardware value. So split. */
    private void killTaint(List<long[]> taint, Varnode v) {
        if (v.isConstant()) {
            return;
        }
        long space = v.getAddress().getAddressSpace().getSpaceID();
        long lo = v.getOffset(), hi = lo + v.getSize();
        List<long[]> remainder = new ArrayList<>();
        for (Iterator<long[]> it = taint.iterator(); it.hasNext();) {
            long[] t = it.next();
            if (t[0] != space || hi <= t[1] || t[2] <= lo) {
                continue;                                   // disjoint: untouched
            }
            it.remove();
            if (t[1] < lo) {
                remainder.add(new long[] { space, t[1], lo });
            }
            if (hi < t[2]) {
                remainder.add(new long[] { space, hi, t[2] });
            }
        }
        taint.addAll(remainder);
    }

    private String hex(Address a) {
        return String.format("0x%x", a.getOffset());
    }

    private void emit(PrintWriter w, String... fields) {
        w.println(String.join("\t", fields));
    }
}
