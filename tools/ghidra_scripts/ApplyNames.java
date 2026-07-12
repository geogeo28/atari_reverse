// Applies a name/comment map to the current program (functions, data labels,
// plate comments, parameter names). Map file path is the first script arg; each
// non-blank, non-'#' line is:
//     fn    <hexaddr> <name>            rename/define a function
//     var   <hexaddr> <name>            label a data address (renames DAT_*)
//     cmt   <hexaddr> <comment ...>     set a plate comment (rest of line)
//     param <hexaddr> <ordinal> <name>  rename an existing parameter by index
//     proto <hexaddr> <name@loc> ...    commit a signature with custom storage;
//                                        loc = stack "off:size" (e.g. dst@4:4) or a
//                                        register "A0"/"D0" (e.g. count@D0). void return.
//
// Use `proto` when Ghidra shows param_1/param_2 in the decompiler but never committed
// them (so `param` finds none) — e.g. stack-arg glue like the blit helpers. `param`
// only renames already-committed params (no storage change).
//
// `param` only renames a parameter Ghidra already recovered (no storage/convention
// change) — safe. For register-glue functions with no recovered params, document the
// register->role map in a `cmt` instead.
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
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.Undefined1DataType;
import ghidra.program.model.data.Undefined2DataType;
import ghidra.program.model.data.Undefined4DataType;
import ghidra.program.model.data.VoidDataType;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Parameter;
import ghidra.program.model.listing.ParameterImpl;
import ghidra.program.model.listing.ReturnParameterImpl;
import ghidra.program.model.listing.Variable;
import ghidra.program.model.listing.VariableStorage;
import ghidra.program.model.symbol.SourceType;
import java.io.BufferedReader;
import java.io.FileReader;
import java.util.ArrayList;
import java.util.List;

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
        int prms = 0;
        int prots = 0;
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
                    case "param": {
                        Function pf = getFunctionAt(addr);
                        String[] pv = parts[2].trim().split("\\s+", 2);
                        if (pf != null && pv.length == 2) {
                            int ord = Integer.parseInt(pv[0]);
                            Parameter[] ps = pf.getParameters();
                            if (ord >= 0 && ord < ps.length) {
                                ps[ord].setName(pv[1].split("#", 2)[0].trim(),
                                        SourceType.USER_DEFINED);
                                prms++;
                            }
                        }
                        break;
                    }
                    case "proto": {
                        Function pf = getFunctionAt(addr);
                        if (pf != null) {
                            List<Variable> ps = new ArrayList<>();
                            for (String spec : parts[2].trim().split("\\s+")) {
                                if (spec.startsWith("#")) {
                                    break;                       // trailing comment
                                }
                                String[] nl = spec.split("@", 2);
                                if (nl.length != 2) {
                                    continue;
                                }
                                VariableStorage vs;
                                DataType dt;
                                if (nl[1].contains(":")) {       // stack: off:size
                                    String[] os = nl[1].split(":");
                                    int sz = Integer.parseInt(os[1]);
                                    vs = new VariableStorage(currentProgram,
                                            Integer.parseInt(os[0]), sz);
                                    dt = undef(sz);
                                } else {                         // register: A0/D0/...
                                    Register reg = currentProgram.getRegister(nl[1]);
                                    vs = new VariableStorage(currentProgram, reg);
                                    dt = undef(reg.getMinimumByteSize());
                                }
                                ps.add(new ParameterImpl(nl[0], dt, vs, currentProgram));
                            }
                            pf.updateFunction(null,
                                    new ReturnParameterImpl(VoidDataType.dataType, currentProgram),
                                    ps, Function.FunctionUpdateType.CUSTOM_STORAGE, true,
                                    SourceType.USER_DEFINED);
                            prots++;
                        }
                        break;
                    }
                    default:
                        break;
                }
            }
        }
        println(String.format("applied %d functions, %d vars, %d comments, %d params, %d protos",
                fns, vars, cmts, prms, prots));
    }

    private static DataType undef(int size) {
        if (size == 1) {
            return Undefined1DataType.dataType;
        }
        if (size == 2) {
            return Undefined2DataType.dataType;
        }
        return Undefined4DataType.dataType;
    }
}