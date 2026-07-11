// Prepares a RAW MEMORY DUMP (from Hatari, of an already-depacked/relocated
// program) for analysis. Unlike PrgLoader, a memory dump has NO GEMDOS header
// and needs NO relocation — it is the live image at its real base, so absolute
// references already resolve. Import it with BinaryLoader at that base
// (-loader-baseAddr), then this script seeds the entry point and disassembles.
//
// Script arg [0] = entry address (hex, e.g. 0x9a000). Defaults to the block start.
//
//@category Atari.ST
//@menupath Tools.Atari.Prep memory dump
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;

public class LoadDump extends GhidraScript {

    @Override
    public void run() throws Exception {
        MemoryBlock[] blocks = currentProgram.getMemory().getBlocks();
        if (blocks.length == 0) {
            println("LoadDump: no memory block — import the dump raw first");
            return;
        }
        blocks[0].setExecute(true);

        String[] args = getScriptArgs();
        Address entry = args.length > 0
                ? toAddr(Long.parseLong(args[0].replace("0x", ""), 16))
                : blocks[0].getStart();

        addEntryPoint(entry);
        createLabel(entry, "entry", true, SourceType.IMPORTED);
        disassemble(entry);
        createFunction(entry, "entry");
        println(String.format("dump prepared: base 0x%x, entry 0x%x — run Analysis > Auto Analyze",
                blocks[0].getStart().getOffset(), entry.getOffset()));
    }
}