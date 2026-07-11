// Applies a name/comment map to the current program (functions, data labels,
// plate comments). Map file path is the first script arg; each non-blank,
// non-'#' line is:
//     fn  <hexaddr> <name>          rename/define a function
//     var <hexaddr> <name>          label a data address (renames DAT_*)
//     cmt <hexaddr> <comment ...>   set a plate comment (rest of line)
//
// fn/var may carry a trailing confidence tag comment, e.g.
//     fn 0x152ac draw_buggy         # confirmed by reading the body
//     fn 0x15872 draw_crash_fx      # ctx  (named from call-context, refinable)
// Everything from the first '#' on an fn/var line is ignored.
//
//@category Atari.ST
//@menupath Tools.Atari.Apply name map
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;
import java.io.BufferedReader;
import java.io.FileReader;

public class ApplyNames extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length == 0) {
            println("ApplyNames: need a map file path as the first argument");
            return;
        }
        int fns = 0;
        int vars = 0;
        int cmts = 0;
        try (BufferedReader r = new BufferedReader(new FileReader(args[0]))) {
            String line;
            while ((line = r.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) {
                    continue;
                }
                String[] parts = line.split("\\s+", 3);
                if (parts.length < 3) {
                    continue;
                }
                Address addr = toAddr(Long.parseLong(parts[1].replace("0x", ""), 16));
                // fn/var take a single name token; strip any trailing "# tag" comment.
                String name = parts[2].split("#", 2)[0].trim().split("\\s+")[0];
                switch (parts[0]) {
                    case "fn":
                        Function func = getFunctionAt(addr);
                        if (func == null) {
                            disassemble(addr);   // handlers reached only via jump tables
                            func = createFunction(addr, name);
                        }
                        if (func != null) {
                            func.setName(name, SourceType.USER_DEFINED);
                            fns++;
                        }
                        break;
                    case "var":
                        createLabel(addr, name, true, SourceType.USER_DEFINED);
                        vars++;
                        break;
                    case "cmt":
                        setPlateComment(addr, parts[2]);
                        cmts++;
                        break;
                    default:
                        break;
                }
            }
        }
        println(String.format("applied %d functions, %d vars, %d comments", fns, vars, cmts));
    }
}