// Exports decompiled C for every function to a text file, plus a function index.
// Intended as a headless post-script; the output path is the first script arg
// (defaults to ./buggyboy_decomp.c in the project dir if omitted).
//
//@category Atari.ST
//@menupath Tools.Atari.Export decompiled C
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import java.io.PrintWriter;

public class ExportDecompC extends GhidraScript {

    static final int TIMEOUT_SEC = 60;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args.length > 0 ? args[0] : "buggyboy_decomp.c";

        DecompInterface ifc = new DecompInterface();
        ifc.openProgram(currentProgram);

        FunctionManager fm = currentProgram.getFunctionManager();
        int total = fm.getFunctionCount();
        int done = 0;
        int failed = 0;

        try (PrintWriter w = new PrintWriter(outPath)) {
            w.println("// Decompiled export of " + currentProgram.getName());
            w.println("// " + total + " functions\n");

            // Index first, so addresses <-> names are easy to scan.
            w.println("// ===== FUNCTION INDEX =====");
            for (Function func : fm.getFunctions(true)) {
                w.printf("//   %s  %-28s  %d bytes%n",
                        func.getEntryPoint(), func.getName(), func.getBody().getNumAddresses());
            }
            w.println();

            for (Function func : fm.getFunctions(true)) {
                if (monitor.isCancelled()) {
                    break;
                }
                w.println("// ---------------------------------------------------------------");
                w.printf("// %s @ %s%n", func.getName(), func.getEntryPoint());
                DecompileResults res = ifc.decompileFunction(func, TIMEOUT_SEC, monitor);
                if (res != null && res.decompileCompleted()
                        && res.getDecompiledFunction() != null) {
                    w.println(res.getDecompiledFunction().getC());
                    done++;
                } else {
                    String err = res == null ? "null" : res.getErrorMessage();
                    w.println("// <decompile failed: " + err + ">");
                    failed++;
                }
            }
        }
        ifc.dispose();
        println(String.format("exported %d/%d functions (%d failed) -> %s",
                done, total, failed, outPath));
    }
}