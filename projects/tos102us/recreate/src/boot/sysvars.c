/* BOOT B2 — the system variables and the vector table: the ROM's boot over [$fc02cc, $fc03b6), and $fc0eba.
 *
 * The head (`src/boot/head/head.S`, ruling D7) ends at `lea $755a,sp`: from there the boot stands on the BIOS's own
 * stack and C can run it. This is the stretch up to `bsr $fc2408` (the BIOS's hardware init, B3's). Nothing here
 * touches a chip: every store is RAM, every read the ROM's own bytes (the header, the device tables' defaults) or the
 * cartridge port's first longword.
 *
 *   $fc02cc  nvbls := 8, fverify := $ff, seekrate := 3, _dskbufp := $16da, _dumpflg := -1, _sysbase := $fc0000,
 *            savptr := $93a, swv_vec := the bare `rts`, drvbits := 0
 *   $fc0308  bsr $fc0eba                       the OS header in RAM; _sysbase := its copy
 *   $fc0314  no diagnostic cartridge?          vectors 2..63 := the bombs handler, its vector number in the top
 *                                              byte; vector 5 (division by zero) := the bare `rte`
 *   $fc0346  autovectors 1..7 := the bare `rte`; then HBL (2) and VBL (4) their handlers, trap #2 the bare `rte`,
 *            trap #13 / #14 the BIOS / XBIOS entries, Line-A the VDI's dispatcher
 *   $fc0382  etv_timer := `rts`, etv_critic := its default, etv_term := `rts`
 *   $fc0392  _vblqueue := $4ce, its 8 slots cleared
 *   $fc03a4  the four device tables' 32 longwords := the ROM's defaults ($fc09ae)
 *
 * THE HANDLERS ARE OURS where this build links one (`BOOT_LINKED_ENTRY`: the HBL and VBL handlers, the two trap
 * entries, the Line-A dispatcher — each the ROM's own instructions, byte-pinned by its battery); the ROM's where it
 * links none (the bare `rte` and `rts`, the bombs handler, the critical-error default: CODE obligations a rebuilt ROM
 * owes, `test_boot_rom_data.py`). The store order inside the span is no surface (RAM only, no chip between): it is
 * kept as the ROM's where that costs nothing, and the two copies move longwords where the header's moves bytes.
 *
 * THE CARTRIDGE ARM (D2 open): a diagnostic cartridge's magic at the port skips the bombs and vector 5, leaving
 * whatever the vectors held. The oracle reads the port as the image's zero, so only the no-cartridge arm runs.
 */
#include <stdint.h>

#include "machine.h"
#include "addrs.h"
#include "m68k_encodings.h"
#include "m68k_idioms.h"
#include "boot/head.h"
#include "boot/sysvars.h"

/* THE THREE LOOPS, each closing on the ROM's `dbf` (the barriers: `machine.h` — a count GCC can read off the
 * source, or a pointer it can re-derive from another, would cost a compare or an indexed mode a pass). */
static void copy_longs(uint8_t *to, const uint8_t *from, int16_t count)
{
    COUNT_BARRIER(count);
    CURSOR_BARRIER(from);
    CURSOR_BARRIER(to);
    for (count--; count >= 0; count--) {
        wr32(to, be32(from));
        to += M68K_LONG_BYTES;
        from += M68K_LONG_BYTES;
    }
}

/* ...each longword `step` past the last: the bombs carry their vector numbers. */
static void fill_longs_stepped(uint8_t *at, int16_t count, uint32_t value, uint32_t step)
{
    COUNT_BARRIER(count);
    REGISTER_BARRIER(step, REGISTER_BARRIER_DATA_CLASS);
    for (count--; count >= 0; count--) {
        wr32(at, value);
        at += M68K_LONG_BYTES;
        value += step;
    }
}

static void fill_longs(uint8_t *at, int16_t count, uint32_t value)
{
    COUNT_BARRIER(count);
    for (count--; count >= 0; count--) {
        wr32(at, value);
        at += M68K_LONG_BYTES;
    }
}

/* $fc0eba — THE OS HEADER IN RAM. The header's first 48 bytes are copied to $940; the word below the copy becomes a
 * `jmp` to the header's reset handler and the copy's own first word (the header's `bra`) a `bra.s` back to that
 * `jmp`; the copy's os_conf takes the word after it; and `_sysbase` names the copy. */
void boot_os_header_to_ram(uint8_t *image)
{
    uint8_t *copy = image + OS_HEADER_RAM;

    copy_longs(copy, image + ROM_OS_HEADER, OS_HEADER_BYTES / M68K_LONG_BYTES);
    wr16(image + OS_HEADER_JUMP, M68K_JMP_ABSOLUTE_LONG);
    wr32(image + OS_HEADER_JUMP_TARGET, be32(copy + OS_HEADER_RESET));
    wr16(copy, OS_HEADER_BRANCH_TO_JUMP);
    wr16(copy + OS_HEADER_CONF, be16(copy + OS_HEADER_DOSDATE));
    wr32(image + SYSVAR_SYSBASE, OS_HEADER_RAM);
}

/* [$fc02cc, $fc03b6) — entered on the BIOS's stack ($755a), A5 = 0 as the head leaves it. */
void boot_sysvars_and_vectors(uint8_t *image)
{
    wr16(image + SYSVAR_NVBLS, BOOT_NVBLS);
    image[SYSVAR_FVERIFY] = BOOT_FVERIFY_ON;
    wr16(image + SYSVAR_SEEKRATE, BOOT_SEEKRATE_3MS);
    wr32(image + SYSVAR_DSKBUFP, BOOT_DISK_BUFFER);
    wr16(image + SYSVAR_DUMPFLG, BOOT_DUMPFLG_IDLE);
    wr32(image + SYSVAR_SYSBASE, ROM_OS_HEADER);
    wr32(image + SYSVAR_SAVPTR, BOOT_SAVE_AREA_TOP);
    wr32(image + SYSVAR_SWV_VEC, ROM_BARE_RTS);
    wr32(image + SYSVAR_DRVBITS, 0);
    boot_os_header_to_ram(image);

    /* Vectors 2..63 the bombs handler, each with its vector number in the top byte; vector 5 a bare `rte`. */
    if (be32(image + CARTRIDGE_PORT) != CARTRIDGE_DIAGNOSTIC_MAGIC) {
        fill_longs_stepped(image + VECTOR_FIRST_BOMB, VECTOR_BOMBS,
                           ROM_BOMBS_ENTRY + ((uint32_t)VECTOR_FIRST_BOMB_NUMBER << VECTOR_NUMBER_SHIFT),
                           1u << VECTOR_NUMBER_SHIFT);
        wr32(image + VECTOR_DIVIDE_BY_ZERO, ROM_BARE_RTE);
    }
    fill_longs(image + VECTOR_AUTOVECTOR_1, AUTOVECTOR_LEVELS, ROM_BARE_RTE);
    wr32(image + VECTOR_VBL, BOOT_LINKED_ENTRY(ISR_VBL, isr_vbl_entry));
    wr32(image + VECTOR_HBL, BOOT_LINKED_ENTRY(ISR_HBL, isr_hbl_entry));
    wr32(image + VECTOR_TRAP_GEM, ROM_BARE_RTE);
    wr32(image + VECTOR_TRAP_BIOS, BOOT_LINKED_ENTRY(BIOS_TRAP13, bios_trap13));
    wr32(image + VECTOR_TRAP_XBIOS, BOOT_LINKED_ENTRY(XBIOS_TRAP14, xbios_trap14));
    wr32(image + VECTOR_LINE_A, BOOT_LINKED_ENTRY(LINEA_ROM_DISPATCH, linea_rom_dispatch));

    wr32(image + SYSVAR_ETV_TIMER, ROM_BARE_RTS);
    wr32(image + SYSVAR_ETV_CRITIC, ROM_ETV_CRITIC_DEFAULT);
    wr32(image + SYSVAR_ETV_TERM, ROM_BARE_RTS);
    wr32(image + SYSVAR_VBLQUEUE, BOOT_VBL_SLOTS);
    fill_longs(image + BOOT_VBL_SLOTS, BOOT_NVBLS, 0);
    copy_longs(image + XCONSTAT_TABLE, image + ROM_XCON_TABLES, XCON_TABLES * XCON_TABLE_DEVICES);
}
