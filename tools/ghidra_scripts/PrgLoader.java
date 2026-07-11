// Rebuilds a raw-imported GEMDOS .PRG into a properly-loaded 68000 program:
//   * parses the 28-byte header (text/data/bss/symbol lengths)
//   * lays TEXT+DATA at BASE and a zero-filled BSS after it
//   * applies the DRI relocation table (adds BASE to every fixup longword, so
//     absolute operands like `lea $xxxx.l` resolve to real in-program addresses)
//   * imports the DRI symbol table as labels
//   * sets the entry point and disassembles it
//
// Works on ANY GEMDOS .PRG. Script args: [0]=path to the .PRG (headless; GUI
// prompts if omitted), [1]=load base as hex, e.g. 0x10000 (optional, default).
//
// GUI usage: File > Import File > <game>.PRG, Format "Raw Binary",
// Language "Motorola 68000" (68000:BE:32:default), skip analysis; then run this.
//
//@category Atari.ST
//@menupath Tools.Atari.Load GEMDOS PRG
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;
import java.io.File;
import java.io.RandomAccessFile;
import java.util.ArrayList;
import java.util.List;

public class PrgLoader extends GhidraScript {

    static long BASE = 0x00010000L;         // load base for TEXT (clear of the 68k vector page)
    static final int PRG_MAGIC = 0x601a;
    static final int HEADER_LEN = 28;
    // DRI symbol type flags (section bits within the type word)
    static final int SYM_BSS = 0x0100;
    static final int SYM_TEXT = 0x0200;
    static final int SYM_DATA = 0x0400;

    @Override
    public void run() throws Exception {
        // Headless: path passed as a script arg. GUI: prompt for it.
        String[] scriptArgs = getScriptArgs();
        File f = scriptArgs.length > 0
                ? new File(scriptArgs[0])
                : askFile("Select the GEMDOS .PRG to load", "Load");
        if (scriptArgs.length > 1) {
            BASE = Long.parseLong(scriptArgs[1].replace("0x", ""), 16);
        }
        byte[] data = readAll(f);

        int magic = u16(data, 0);
        if (magic != PRG_MAGIC) {
            throw new Exception(String.format("not a GEMDOS PRG (magic=0x%04x)", magic));
        }
        long tlen = u32(data, 2);
        long dlen = u32(data, 6);
        long blen = u32(data, 10);
        long slen = u32(data, 14);
        long symOff = HEADER_LEN + tlen + dlen;
        long relocOff = symOff + slen;
        int imageLen = (int) (tlen + dlen);          // TEXT+DATA load contiguously
        byte[] image = new byte[imageLen];
        System.arraycopy(data, HEADER_LEN, image, 0, imageLen);
        println(String.format("PRG: text=0x%x data=0x%x bss=0x%x sym=0x%x", tlen, dlen, blen, slen));

        Memory mem = currentProgram.getMemory();
        for (MemoryBlock b : mem.getBlocks()) {      // drop the flat raw-import block(s)
            mem.removeBlock(b, monitor);
        }

        MemoryBlock text = mem.createInitializedBlock(
                "TEXT", toAddr(BASE), imageLen, (byte) 0, monitor, false);
        mem.setBytes(toAddr(BASE), image);
        text.setExecute(true);
        if (blen > 0) {
            mem.createInitializedBlock(
                    "BSS", toAddr(BASE + tlen + dlen), blen, (byte) 0, monitor, false);
        }

        List<Long> fixups = parseRelocs(data, relocOff);
        for (long off : fixups) {                    // relocate: pointer += load base
            Address a = toAddr(BASE + off);
            mem.setInt(a, mem.getInt(a) + (int) BASE);
        }
        println("applied " + fixups.size() + " relocations");

        int nsym = (int) (slen / 14);
        for (int i = 0; i < nsym; i++) {
            int p = (int) symOff + i * 14;
            String name = symName(data, p);
            int typ = u16(data, p + 8);
            long val = u32(data, p + 10);
            Long addr = symAddress(typ, val, tlen, dlen);
            if (addr == null || name.isEmpty()) {
                continue;
            }
            // Label only: TEXT-section symbols mix routines with inline data
            // (flag bytes sit 1 byte apart), so let auto-analysis decide functions.
            createLabel(toAddr(addr), name, true, SourceType.IMPORTED);
        }
        println("imported " + nsym + " symbols");

        Address entry = toAddr(BASE);
        addEntryPoint(entry);
        createLabel(entry, "_start", true, SourceType.IMPORTED);
        disassemble(entry);
        createFunction(entry, "_start");
        println(String.format("entry @ 0x%x -- now run Analysis > Auto Analyze", BASE));
    }

    private byte[] readAll(File f) throws Exception {
        try (RandomAccessFile r = new RandomAccessFile(f, "r")) {
            byte[] b = new byte[(int) r.length()];
            r.readFully(b);
            return b;
        }
    }

    private int u16(byte[] d, int p) {
        return ((d[p] & 0xff) << 8) | (d[p + 1] & 0xff);
    }

    private long u32(byte[] d, int p) {
        return ((long) (d[p] & 0xff) << 24) | ((d[p + 1] & 0xff) << 16)
                | ((d[p + 2] & 0xff) << 8) | (d[p + 3] & 0xff);
    }

    private String symName(byte[] d, int p) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 8; i++) {
            int c = d[p + i] & 0xff;
            if (c == 0) {
                break;
            }
            sb.append((char) c);
        }
        return sb.toString();
    }

    private Long symAddress(int typ, long val, long tlen, long dlen) {
        if ((typ & SYM_TEXT) != 0) {
            return BASE + val;
        }
        if ((typ & SYM_DATA) != 0) {
            return BASE + tlen + val;
        }
        if ((typ & SYM_BSS) != 0) {
            return BASE + tlen + dlen + val;
        }
        return null;
    }

    private List<Long> parseRelocs(byte[] d, long relocOff) {
        List<Long> fx = new ArrayList<>();
        if (relocOff >= d.length) {
            return fx;
        }
        long first = u32(d, (int) relocOff);
        if (first == 0) {
            return fx;
        }
        long cur = first;
        fx.add(first);
        int p = (int) relocOff + 4;
        while (p < d.length) {
            int b = d[p] & 0xff;
            p++;
            if (b == 0) {
                break;
            }
            cur += (b == 1) ? 254 : b;
            fx.add(cur);
        }
        return fx;
    }
}