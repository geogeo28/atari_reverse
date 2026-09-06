// Pins a register to a constant over the whole program, so the decompiler resolves
// register-relative operands to absolute addresses.
//
//   SetRegisterValue.java <register> <hex value>      e.g.  SetRegisterValue.java a4 0x24f1a
//
// Why: Alcyon/DRI C small model addresses every global as `n(a4)`, with a4 set once by the
// crt0 to the BSS/DATA boundary (see tools/prg_relayout.py). Ghidra has no way to know that
// value, so `decomp.c` is full of `*(a4 + -8560)` arithmetic that no `var 0x<addr> <name>`
// line can attach a name to. Ghidra's decompiler reads the ProgramContext's register values
// at each function's entry and emits them as tracked constants, so setting a4 here turns the
// same operand into a plain `DAT_<address>`.
//
// Run it as a PRE-script, after PrgLoader and before auto-analysis, so analysis and the
// decompiler both see the value. Re-running is safe: setValue overwrites the range.
//
// The value is set over every memory block, not just TEXT, which costs nothing and keeps the
// script independent of how the loader named its blocks.
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
            println("SetRegisterValue: need <register> <hex value>, e.g. a4 0x24f1a");
            return;
        }
        Register reg = currentProgram.getRegister(args[0]);
        if (reg == null) {
            println("SetRegisterValue: no register named '" + args[0] + "' in this language");
            return;
        }
        BigInteger value = new BigInteger(args[1].replaceFirst("^0[xX]", ""), 16);

        ProgramContext ctx = currentProgram.getProgramContext();
        int blocks = 0;
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            ctx.setValue(reg, b.getStart(), b.getEnd(), value);
            blocks++;
        }
        println(String.format("%s = 0x%s over %d memory block(s)",
                reg.getName(), value.toString(16), blocks));
    }
}
