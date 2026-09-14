// Prepares a raw-imported ATARI TOS ROM IMAGE for analysis.
//
// A ROM is neither a .PRG (PrgLoader: header + relocation table) nor a memory dump
// (LoadDump: one flat block at a base). It is an absolute image that already sits at
// its run address, plus the address ranges that are NOT in the file and without
// which most of its operands resolve to nothing:
//
//   * RAM_VEC     $000000..$0003FF  the 68000 exception vector table.
//   * SYSVAR      $000400..$000FFF  the TOS system variables, VOLATILE: `_frclock` ($466),
//                                   `_hz_200` ($4BA) and the ACIA/MFP iorec records at
//                                   $C54/$C76/$D84 are written by interrupt handlers, so a
//                                   non-volatile block lets the decompiler fold a spin loop
//                                   (`Vsync`, $FC07D0) into `do {} while (true)`.
//   * RAM         $001000..os_end   the OS's own BSS and buffers. os_end is read from the OS
//                                   header ($0c), so a `move.l $4ba.w,d0` lands on a
//                                   labelled address instead of on no block at all.
//   * GEM BSS     os_end..gem_end   GEM's (VDI/AES/desktop) static data, which lives
//                                   ABOVE the OS BSS. gem_end is the second longword
//                                   of the GEM memory-usage parameter block the header
//                                   points at ($14) -- on TOS 1.02 US: $CA00.
//   * I/O page    $FFFF8000..FFFFFFFF  the ST hardware registers (docs/hardware-map.md),
//                                   marked volatile so the decompiler does not fold a
//                                   repeated register read into one value.
//   * I/O alias   $FF8000..$FFFFFF  the same registers through their 24-bit addresses, which
//                                   is how TOS itself writes several of them (`move.w d0,
//                                   ($00ff8240).l` in the VDI's vs_color, the blitter's
//                                   `lea $00ff8a3c,a5`). Volatile for the same reason.
//   * CARTRIDGE   $FA0000..FBFFFF   the ROM port the reset code probes for the $FA52235F
//                                   magic before it does anything else.
//
// What it does: rename the imported block ROM and mark it read-only + execute, create
// those uninitialised blocks, label the OS header fields and the MUPB, then set
// the entry point to the header's reset PC ($04) and disassemble from it.
//
// Script args: [0] = load base as hex (default 0xFC0000) -- must equal the address the
// image was imported at (`-loader-baseAddr`) AND the header's own os_beg ($08), which the
// script checks: a ROM is absolute, so a base that disagrees makes every operand wrong.
//
// Seeding of the dispatch tables is NOT done here: an `fn` line in a name map creates a
// function by itself, so the entries are seeded by running ApplyNames over a seed file
// ahead of analysis (tools/load_rom.sh).
//
//@category Atari.ST
//@menupath Tools.Atari.Load TOS ROM
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;
import ghidra.app.script.GhidraScript;

public class RomLoader extends GhidraScript {

    static final long DEFAULT_BASE = 0x00FC0000L;
    static final int OS_BRA = 0x602e;               // header word 0: bra.s to the reset PC

    // OS header field offsets (docs/binary-formats.md, "The TOS ROM header").
    static final int OSH_VERSION = 0x02;
    static final int OSH_RESET_PC = 0x04;
    static final int OSH_OS_BEG = 0x08;
    static final int OSH_OS_END = 0x0c;
    static final int OSH_OS_RSV1 = 0x10;
    static final int OSH_OS_MAGIC = 0x14;           // -> GEM memory-usage parameter block
    static final int OSH_OS_DATE = 0x18;
    static final int OSH_OS_CONF = 0x1c;
    static final int OSH_OS_DOSDATE = 0x1e;
    static final int OSH_P_ROOT = 0x20;
    static final int OSH_PKBSHIFT = 0x24;
    static final int OSH_P_RUN = 0x28;
    static final int OSH_P_RSV2 = 0x2c;

    static final int MUPB_MAGIC = 0x87654321;
    static final int MUPB_GEM_END = 0x04;           // longword: top of GEM's RAM usage
    static final int MUPB_GEM_ENTRY = 0x08;         // longword: GEM entry point in ROM

    static final long VECTORS_BASE = 0x0L;          // 68000 exception vector table
    static final long VECTORS_LEN = 0x400L;
    static final long SYSVAR_BASE = 0x400L;         // TOS system variables, interrupt-written
    static final long SYSVAR_LEN = 0xC00L;
    static final long RAM_BASE = SYSVAR_BASE + SYSVAR_LEN;      // OS BSS and buffers, up to os_end
    static final long IO_BASE = 0xFFFF8000L;        // ST hardware registers
    static final long IO_LEN = 0x8000L;
    static final long IO_ALIAS_BASE = 0x00FF8000L;  // the same registers, 24-bit addressing
    static final long CART_BASE = 0x00FA0000L;      // ROM cartridge port
    static final long CART_LEN = 0x20000L;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        long base = args.length > 0 ? Long.parseLong(args[0].replace("0x", ""), 16) : DEFAULT_BASE;
        Address rom = toAddr(base);

        Memory mem = currentProgram.getMemory();
        MemoryBlock image = mem.getBlock(rom);
        if (image == null) {
            throw new Exception(String.format(
                    "no memory block at 0x%x -- import the ROM raw at that base first", base));
        }
        int magic = getShort(rom) & 0xffff;
        if (magic != OS_BRA) {
            throw new Exception(String.format(
                    "not a TOS ROM header at 0x%x (first word 0x%04x, expected 0x%04x)",
                    base, magic, OS_BRA));
        }
        // The ROM publishes its own load address, so a base that disagrees with the header is
        // a mis-import, not a choice: every absolute operand in the image would point elsewhere.
        long osBeg = getInt(rom.add(OSH_OS_BEG)) & 0xffffffffL;
        if (osBeg != base) {
            throw new Exception(String.format(
                    "base 0x%x disagrees with the header's os_beg 0x%x -- re-import the image"
                    + " with -loader-baseAddr %x", base, osBeg, osBeg));
        }
        image.setName("ROM");
        image.setRead(true);
        image.setWrite(false);
        image.setExecute(true);

        long osEnd = getInt(rom.add(OSH_OS_END)) & 0xffffffffL;
        if (osEnd <= RAM_BASE) {
            throw new Exception(String.format(
                    "os_end 0x%x is inside the system-variable page -- not a TOS OS header", osEnd));
        }
        long gemEnd = gemRamEnd(rom);
        createUninit("RAM_VEC", VECTORS_BASE, VECTORS_LEN, false);
        createUninit("SYSVAR", SYSVAR_BASE, SYSVAR_LEN, true);
        createUninit("RAM", RAM_BASE, osEnd - RAM_BASE, false);
        if (gemEnd > osEnd) {
            createUninit("GEMBSS", osEnd, gemEnd - osEnd, false);
        }
        createUninit("IO", IO_BASE, IO_LEN, true);
        createUninit("IO_ALIAS", IO_ALIAS_BASE, IO_LEN, true);
        createUninit("CARTRIDGE", CART_BASE, CART_LEN, false);

        labelHeader(rom);

        Address entry = toAddr(getInt(rom.add(OSH_RESET_PC)) & 0xffffffffL);
        addEntryPoint(entry);
        createLabel(entry, "os_reset", true, SourceType.IMPORTED);
        disassemble(entry);
        createFunction(entry, "os_reset");
        println(String.format(
                "TOS ROM loaded: base 0x%x, version 0x%04x, reset PC 0x%x, os_end 0x%x, gem_end 0x%x",
                base, getShort(rom.add(OSH_VERSION)) & 0xffff, entry.getOffset(), osEnd, gemEnd));
    }

    /** Top of GEM's RAM usage, from the MUPB the header points at; 0 if there is none. */
    private long gemRamEnd(Address rom) throws Exception {
        long mupb = getInt(rom.add(OSH_OS_MAGIC)) & 0xffffffffL;
        MemoryBlock block = getMemoryBlock(toAddr(mupb));
        if (block == null || !block.isInitialized()) {
            println(String.format("os_magic 0x%x is outside the image -- no GEM BSS block", mupb));
            return 0;
        }
        Address at = toAddr(mupb);
        if (getInt(at) != MUPB_MAGIC) {
            println(String.format("no MUPB magic at 0x%x -- no GEM BSS block", mupb));
            return 0;
        }
        createLabel(at, "gem_mupb", true, SourceType.IMPORTED);
        setPlateComment(at, String.format(
                "GEM memory-usage parameter block: magic 0x%08x, GEM RAM top 0x%x, GEM entry 0x%x",
                MUPB_MAGIC, getInt(at.add(MUPB_GEM_END)), getInt(at.add(MUPB_GEM_ENTRY))));
        return getInt(at.add(MUPB_GEM_END)) & 0xffffffffL;
    }

    private void createUninit(String name, long start, long length, boolean volatileBlock)
            throws Exception {
        Memory mem = currentProgram.getMemory();
        MemoryBlock block = mem.createUninitializedBlock(name, toAddr(start), length, false);
        block.setRead(true);
        block.setWrite(true);
        block.setExecute(false);
        block.setVolatile(volatileBlock);
        println(String.format("  block %-9s 0x%06x..0x%06x", name, start, start + length - 1));
    }

    private void labelHeader(Address rom) throws Exception {
        label(rom, OSH_VERSION, "os_version");
        label(rom, OSH_RESET_PC, "os_reset_pc");
        label(rom, OSH_OS_BEG, "os_beg");
        label(rom, OSH_OS_END, "os_end");
        label(rom, OSH_OS_RSV1, "os_rsv1");
        label(rom, OSH_OS_MAGIC, "os_magic");
        label(rom, OSH_OS_DATE, "os_date");
        label(rom, OSH_OS_CONF, "os_conf");
        label(rom, OSH_OS_DOSDATE, "os_dosdate");
        label(rom, OSH_P_ROOT, "os_p_root");
        label(rom, OSH_PKBSHIFT, "os_pkbshift");
        label(rom, OSH_P_RUN, "os_p_run");
        label(rom, OSH_P_RSV2, "os_p_rsv2");
        createLabel(rom, "os_header", true, SourceType.IMPORTED);
        setPlateComment(rom, String.format(
                "TOS OS header. version 0x%04x, date 0x%08x, os_beg 0x%x, os_end 0x%x",
                getShort(rom.add(OSH_VERSION)) & 0xffff, getInt(rom.add(OSH_OS_DATE)),
                getInt(rom.add(OSH_OS_BEG)), getInt(rom.add(OSH_OS_END))));
    }

    private void label(Address rom, int offset, String name) throws Exception {
        createLabel(rom.add(offset), name, true, SourceType.IMPORTED);
    }
}
