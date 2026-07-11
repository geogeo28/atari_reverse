// Dumps the current program's names back into names.txt format (fn/var/cmt),
// so edits made in the GUI can be recovered into the reproducible name map.
// Output path is the first script arg (default names_dump.txt).
//
// Emits: non-default function names (fn), non-default data labels (var), and
// PLATE comments (cmt). Addresses are Ghidra addresses, matching names.txt.
// It does NOT reproduce names.txt's section grouping or "# ctx" tags — diff it
// against your curated names.txt and merge new/changed lines by hand.
//
//@category Atari.ST
//@menupath Tools.Atari.Dump names
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressIterator;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolTable;
import ghidra.program.model.symbol.SymbolType;
import ghidra.program.model.symbol.SourceType;
import java.io.PrintWriter;
import java.util.Map;
import java.util.TreeMap;

public class DumpNames extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String out = args.length > 0 ? args[0] : "names_dump.txt";

        TreeMap<Long, String> fns = new TreeMap<>();
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            if (f.getSymbol().getSource() != SourceType.DEFAULT && !f.isThunk()) {
                fns.put(f.getEntryPoint().getOffset(), f.getName());
            }
        }

        TreeMap<Long, String> vars = new TreeMap<>();
        SymbolTable st = currentProgram.getSymbolTable();
        for (Symbol s : st.getAllSymbols(false)) {          // false = skip dynamic FUN_/DAT_
            if (s.getSource() != SourceType.DEFAULT && s.getSymbolType() == SymbolType.LABEL) {
                vars.put(s.getAddress().getOffset(), s.getName());
            }
        }

        TreeMap<Long, String> cmts = new TreeMap<>();
        Listing lst = currentProgram.getListing();
        AddressIterator it = lst.getCommentAddressIterator(
                CodeUnit.PLATE_COMMENT, currentProgram.getMemory(), true);
        while (it.hasNext()) {
            Address a = it.next();
            String c = lst.getComment(CodeUnit.PLATE_COMMENT, a);
            if (c != null) {
                cmts.put(a.getOffset(), c.replace("\n", " ").trim());
            }
        }

        try (PrintWriter w = new PrintWriter(out)) {
            w.println("# Dumped from " + currentProgram.getName()
                    + " by DumpNames. fn/var/cmt, Ghidra addresses. Merge into names.txt.");
            for (Map.Entry<Long, String> e : fns.entrySet()) {
                w.printf("fn 0x%x %s%n", e.getKey(), e.getValue());
            }
            for (Map.Entry<Long, String> e : vars.entrySet()) {
                w.printf("var 0x%x %s%n", e.getKey(), e.getValue());
            }
            for (Map.Entry<Long, String> e : cmts.entrySet()) {
                w.printf("cmt 0x%x %s%n", e.getKey(), e.getValue());
            }
        }
        println(String.format("dumped %d fn, %d var, %d cmt -> %s",
                fns.size(), vars.size(), cmts.size(), out));
    }
}