// Creates a function at every disassembled instruction that belongs to no function, so
// that code stops being invisible in the decompiled export.
//
// Ghidra creates functions at CALL targets by itself. What it leaves behind is code it
// disassembled by following flow but never attributed: branch-only entry points
// (`bra`/`jmp` tails, and every arm of a jump table after the first), and the code past
// a flow-override site. Those instructions are proven code — the flow follower reached
// them — but ExportDecompC walks the function manager, so none of it is exported.
//
// Deliberately NOT a linear-sweep seeder: it only ever seeds addresses Ghidra already
// disassembled. Seeding from a linear sweep of the raw text segment invents functions
// inside data, which desyncs on the ST (see docs/m68k-disassembly.md).
//
// One pass suffices: creating a function does not invalidate the instruction iterator,
// and the new body covers its own instructions, so the next uncovered instruction the
// iterator reaches is the next entry point to seed.
//
// Run AFTER auto-analysis (and after LineAResolve). Reports every address it seeds.
//
//@category Atari.ST
//@menupath Tools.Atari.Seed functions from orphan code
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

public class SeedFunctions extends GhidraScript {

    @Override
    public void run() throws Exception {
        int seeded = 0;
        int failed = 0;
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction insn = it.next();
            Address at = insn.getMinAddress();
            if (getFunctionContaining(at) != null) {
                continue;
            }
            if (createFunction(at, null) == null) {
                printerr("WARNING: createFunction failed at " + at + " -- orphan code stays unexported");
                failed++;
                continue;
            }
            println("  seeded " + at);
            seeded++;
        }
        println("seeded " + seeded + " functions from orphan code"
                + (failed == 0 ? "" : ", " + failed + " FAILED"));
    }
}
