// Annotates every 68k OS trap in the current program with its call name.
//   trap #1  -> GEMDOS  (selector from the preceding `move.w #sel,-(sp)`)
//   trap #13 -> BIOS
//   trap #14 -> XBIOS
//   trap #2  -> GEM: AES (d0=200) or VDI (d0=115), from the preceding move to d0
// Comments are added as EOL comments at each trap site.
//
// Run AFTER PrgLoader + Auto Analyze, so traps are disassembled.
//
//@category Atari.ST
//@menupath Tools.Atari.Annotate OS traps
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.SourceType;
import ghidra.util.exception.DuplicateNameException;
import java.util.HashMap;
import java.util.Map;

public class AtariOsTrapAnnotate extends GhidraScript {

    static final int LOOKBACK = 16;      // instructions to scan back for the selector/d0
    static final int WRAPPER_MAX_INSNS = 12;   // a thin OS wrapper is at most this many instructions
    static final int AES_FID = 200;
    static final int VDI_FID = 115;

    static final Map<Integer, String> GEMDOS = new HashMap<>();
    static final Map<Integer, String> BIOS = new HashMap<>();
    static final Map<Integer, String> XBIOS = new HashMap<>();
    static {
        put(GEMDOS, 0x00, "Pterm0"); put(GEMDOS, 0x01, "Cconin"); put(GEMDOS, 0x02, "Cconout");
        put(GEMDOS, 0x09, "Cconws"); put(GEMDOS, 0x0A, "Cconrs"); put(GEMDOS, 0x20, "Super");
        put(GEMDOS, 0x2F, "Fgetdta"); put(GEMDOS, 0x30, "Sversion"); put(GEMDOS, 0x3C, "Fcreate");
        put(GEMDOS, 0x3D, "Fopen"); put(GEMDOS, 0x3E, "Fclose"); put(GEMDOS, 0x3F, "Fread");
        put(GEMDOS, 0x40, "Fwrite"); put(GEMDOS, 0x41, "Fdelete"); put(GEMDOS, 0x42, "Fseek");
        put(GEMDOS, 0x48, "Malloc"); put(GEMDOS, 0x49, "Mfree"); put(GEMDOS, 0x4A, "Mshrink");
        put(GEMDOS, 0x4B, "Pexec"); put(GEMDOS, 0x4C, "Pterm"); put(GEMDOS, 0x4E, "Fsfirst");
        put(GEMDOS, 0x4F, "Fsnext"); put(GEMDOS, 0x56, "Frename");

        put(BIOS, 0x01, "Bconstat"); put(BIOS, 0x02, "Bconin"); put(BIOS, 0x03, "Bconout");
        put(BIOS, 0x04, "Rwabs"); put(BIOS, 0x05, "Setexc"); put(BIOS, 0x07, "Getbpb");
        put(BIOS, 0x0A, "Drvmap"); put(BIOS, 0x0B, "Kbshift");

        put(XBIOS, 0x00, "Initmous"); put(XBIOS, 0x02, "Physbase"); put(XBIOS, 0x03, "Logbase");
        put(XBIOS, 0x04, "Getrez"); put(XBIOS, 0x05, "Setscreen"); put(XBIOS, 0x06, "Setpalette");
        put(XBIOS, 0x07, "Setcolor"); put(XBIOS, 0x08, "Floprd"); put(XBIOS, 0x09, "Flopwr");
        put(XBIOS, 0x11, "Random"); put(XBIOS, 0x1F, "Vsync"); put(XBIOS, 0x20, "Supexec");
        put(XBIOS, 0x26, "Supexec"); put(XBIOS, 0x28, "Xbtimer"); put(XBIOS, 0x2A, "Dosound");
    }

    private static void put(Map<Integer, String> m, int k, String v) {
        m.put(k, v);
    }

    @Override
    public void run() throws Exception {
        int annotated = 0;
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction insn = it.next();
            if (!"trap".equals(insn.getMnemonicString())) {
                continue;
            }
            Scalar vecOp = insn.getScalar(0);
            if (vecOp == null) {
                continue;
            }
            int vec = (int) vecOp.getUnsignedValue();
            String comment = describe(vec, insn);
            if (comment != null) {
                setEOLComment(insn.getMinAddress(), comment);
                annotated++;
            }
        }
        println("annotated " + annotated + " trap sites");
        renameWrappers();
    }

    // Rename functions whose whole body is a single OS trap (a thin wrapper) to
    // e.g. `xbios_setpalette`. Only touches auto-named (FUN_*) functions, so
    // imported symbols and hand-named functions are left alone.
    private void renameWrappers() throws Exception {
        int renamed = 0;
        FunctionManager fm = currentProgram.getFunctionManager();
        for (Function func : fm.getFunctions(true)) {
            if (monitor.isCancelled()) {
                break;
            }
            if (func.getSymbol().getSource() != SourceType.DEFAULT) {
                continue;
            }
            Instruction only = null;
            int ntrap = 0;
            int count = 0;
            InstructionIterator bit =
                    currentProgram.getListing().getInstructions(func.getBody(), true);
            while (bit.hasNext()) {
                Instruction i = bit.next();
                count++;
                if ("trap".equals(i.getMnemonicString())) {
                    ntrap++;
                    only = i;
                }
            }
            if (ntrap != 1 || count > WRAPPER_MAX_INSNS) {
                continue;
            }
            Scalar vecOp = only.getScalar(0);
            if (vecOp == null) {
                continue;
            }
            String name = wrapperName((int) vecOp.getUnsignedValue(), only);
            if (name == null) {
                continue;
            }
            try {
                func.setName(name, SourceType.USER_DEFINED);
            } catch (DuplicateNameException e) {
                func.setName(name + "_" + func.getEntryPoint(), SourceType.USER_DEFINED);
            }
            renamed++;
        }
        println("renamed " + renamed + " single-trap wrappers");
    }

    // Identifier form of the OS call for a function rename, or null if unresolved.
    private String wrapperName(int vec, Instruction trap) throws Exception {
        if (vec == 1) {
            return tableName("gemdos", GEMDOS, precedingPushWord(trap));
        }
        if (vec == 13) {
            return tableName("bios", BIOS, precedingPushWord(trap));
        }
        if (vec == 14) {
            return tableName("xbios", XBIOS, precedingPushWord(trap));
        }
        if (vec == 2) {
            int fid = precedingD0Word(trap);
            if (fid == AES_FID) {
                return "gem_aes";
            }
            if (fid == VDI_FID) {
                return "gem_vdi";
            }
        }
        return null;
    }

    private String tableName(String prefix, Map<Integer, String> table, int sel) {
        String fn = table.get(sel);
        return fn == null ? null : prefix + "_" + fn.toLowerCase();
    }

    private String describe(int vec, Instruction trap) throws Exception {
        if (vec == 1) {
            return named("GEMDOS", GEMDOS, precedingPushWord(trap));
        }
        if (vec == 13) {
            return named("BIOS", BIOS, precedingPushWord(trap));
        }
        if (vec == 14) {
            return named("XBIOS", XBIOS, precedingPushWord(trap));
        }
        if (vec == 2) {
            int fid = precedingD0Word(trap);
            if (fid == AES_FID) {
                return "GEM AES call";
            }
            if (fid == VDI_FID) {
                return "GEM VDI call";
            }
            return "GEM trap (d0=?)";
        }
        return null;
    }

    private String named(String layer, Map<Integer, String> table, int sel) {
        if (sel < 0) {
            return layer + " (selector=?)";
        }
        String fn = table.get(sel);
        return String.format("%s %s ($%x)", layer, fn == null ? "?" : fn, sel);
    }

    // Nearest preceding `move.w #imm,-(sp)` (opcode 0x3f3c) -> imm, else -1.
    private int precedingPushWord(Instruction trap) throws Exception {
        Instruction cur = getInstructionBefore(trap.getMinAddress());
        for (int hop = 0; cur != null && hop < LOOKBACK; hop++) {
            byte[] b = cur.getBytes();
            if (b.length >= 4 && u16(b, 0) == 0x3f3c) {
                return u16(b, 2);
            }
            cur = getInstructionBefore(cur.getMinAddress());
        }
        return -1;
    }

    // Nearest preceding load of a word into d0: move.w #imm,d0 (0x303c) or moveq (0x70xx).
    private int precedingD0Word(Instruction trap) throws Exception {
        Instruction cur = getInstructionBefore(trap.getMinAddress());
        for (int hop = 0; cur != null && hop < LOOKBACK; hop++) {
            byte[] b = cur.getBytes();
            if (b.length >= 4 && u16(b, 0) == 0x303c) {
                return u16(b, 2);
            }
            if (b.length >= 2 && (u16(b, 0) & 0xff00) == 0x7000) {   // moveq #n,d0
                return u16(b, 0) & 0xff;
            }
            cur = getInstructionBefore(cur.getMinAddress());
        }
        return -1;
    }

    private int u16(byte[] d, int p) {
        return ((d[p] & 0xff) << 8) | (d[p + 1] & 0xff);
    }
}