// Pins a register to a constant, so the decompiler resolves register-relative operands to
// absolute addresses. Over the whole program by default, or over one address range.
//
//   SetRegisterValue.java <register> <hex value> [start_hex] [end_hex]
//       e.g.  SetRegisterValue.java a4 0x24f1a            (program-wide)
//             SetRegisterValue.java a5 0 0xfc0688 0xfc4e5d   (one range)
//
// Why: Alcyon/DRI C small model addresses every global as `n(a4)`, with a4 set once by the
// crt0 to the BSS/DATA boundary (see tools/prg_relayout.py). Ghidra has no way to know that
// value, so `decomp.c` is full of `*(a4 + -8560)` arithmetic that no `var 0x<addr> <name>`
// line can attach a name to. Ghidra's decompiler reads the ProgramContext's register values
// at each function's entry and emits them as tracked constants, so setting a4 here turns the
// same operand into a plain `DAT_<address>`.
//
// The range form is for an image where the same register is a base in one component and
// something else elsewhere: a TOS ROM's BIOS/XBIOS is entered with a5 = 0 by its dispatcher
// (`suba.l a5,a5`), while the boot and GEM use a5 as a live pointer (projects/tos102us/run.sh,
// COMPONENTS.md "The a5 base register"). A value pinned where it is wrong is worse than no
// pin: the decompiler resolves operands off it just as confidently.
//
// Run it as a PRE-script, after the loader and before auto-analysis, so analysis and the
// decompiler both see the value. Re-running is safe: setValue overwrites the range.
//
//@category Atari.ST
//@menupath Tools.Atari.Set register value
import ghidra.app.script.GhidraScript;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.ProgramContext;
import ghidra.program.model.mem.MemoryBlock;
import java.math.BigInteger;

public class SetRegisterValue extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            println("SetRegisterValue: need <register> <hex value> [start_hex] [end_hex],"
                    + " e.g. a4 0x24f1a");
            return;
        }
        Register reg = currentProgram.getRegister(args[0]);
        if (reg == null) {
            println("SetRegisterValue: no register named '" + args[0] + "' in this language");
            return;
        }
        BigInteger value = new BigInteger(hex(args[1]), 16);
        ProgramContext ctx = currentProgram.getProgramContext();

        if (args.length >= 4) {
            long start = Long.parseLong(hex(args[2]), 16);
            long end = Long.parseLong(hex(args[3]), 16);
            ctx.setValue(reg, toAddr(start), toAddr(end), value);
            println(String.format("%s = 0x%s over 0x%x..0x%x",
                    reg.getName(), value.toString(16), start, end));
            return;
        }

        // Every memory block, not just TEXT: costs nothing and keeps the script independent
        // of how the loader named its blocks.
        int blocks = 0;
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            ctx.setValue(reg, b.getStart(), b.getEnd(), value);
            blocks++;
        }
        println(String.format("%s = 0x%s over %d memory block(s)",
                reg.getName(), value.toString(16), blocks));
    }

    private static String hex(String arg) {
        return arg.replaceFirst("^0[xX]", "");
    }
}
