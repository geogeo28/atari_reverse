/* entry.c — the Line-A exception, the VDI's `trap #2` entry and its dispatcher (`vdi/entry.h` says what each is).
 *
 * EVERY READ HAPPENS WHERE THE ROM MAKES IT. A caller's parameter block, contrl array and workstation records may
 * lie anywhere — over the Line-A pointers the entry stores, over the fields the dispatcher copies into — so each
 * value is read at the instruction the ROM reads it at, after every store the ROM made before it, and a pointer
 * the ROM loads ONCE into a register (`movea.l (a0)+,a2`, `movea.l $299e,a5`) is held in a local.
 *
 * THE 24-BIT BUS. The pointers a program hands in are longwords whose top byte the 68000 does not drive; each is
 * STORED as it came and DEREFERENCED through `bus_dereference`.
 */
#include <stdint.h>

#include "addrs.h"
#include "m68k_idioms.h"
#include "machine.h"
#include "staged_call.h"
#include "vdi/entry.h"
#include "vdi/font.h"
#include "vdi/transcribed.h"
#include "vdi/vdi.h"
#include "vdi/workstation.h"

/* The $Axxx word the stacked PC names, which the handler steps past (`addq.l #2,a1`). */
#define LINEA_OPCODE_WORD_BYTES 2
/* The copy's capacity as the entry counts it: words (`move.w #1024,d1`). */
#define VDI_PTSIN_COPY_WORDS (VDI_PTSIN_COPY_BYTES / VDI_WORD_BYTES)

/* $fc9f0c — the Line-A exception. The ROM reads the opcode word BEFORE it stores the stepped PC (an order only an
 * $Axxx word lying in the frame's own PC slot could show, which no case stages: kept as the ROM's, unpinned), and
 * serves only 0..LINEA_OPCODE_LAST, compared UNSIGNED (`bhi`) after the mask. The table is read where the ROM
 * keeps it. */
TRANSCRIBED_CORE
void linea_dispatch(uint8_t *image, uint32_t frame, uint32_t registers[STAGED_REGISTERS])
{
    uint32_t opcode_at = be32(image + frame + EXCEPTION_FRAME_PC);
    uint16_t opcode = be16(image + bus_dereference(opcode_at)) & LINEA_OPCODE_MASK;

    wr32(image + frame + EXCEPTION_FRAME_PC, opcode_at + LINEA_OPCODE_WORD_BYTES);
    if (opcode > LINEA_OPCODE_LAST)
        return;
    call_vector_registers(image, be32(image + table_entry(LINEA_OPCODE_TABLE, opcode, VDI_LONG_BYTES)), registers);
}

/* One workstation field copied into the Line-A variable (or VDI word) at `destination`. */
static inline void copy_field_word(uint8_t *image, uint32_t destination, const uint8_t *record, uint32_t field)
{
    wr16(image + destination, be16(record + field));
}

static inline void copy_field_long(uint8_t *image, uint32_t destination, const uint8_t *record, uint32_t field)
{
    wr32(image + destination, be32(record + field));
}

/* The workstation with `handle`, walked from the physical record by WS_NEXT until a zero link — or 0 when none
 * has it. The FIRST match wins: v_opnvwk can link two records with one handle. The link is tested as the whole
 * longword the ROM tests. */
static uint32_t workstation_with(const uint8_t *image, int16_t handle)
{
    uint32_t work = VDI_PHYS_WORK;

    do {
        if (handle_of(image, work) == handle)
            return work;
        work = next_of(image, work);
    } while (work);
    return 0;
}

/* $fcaa40..$fcab14: `work` made current and its fields copied into Line-A, in the ROM's order (`test/vdi.py`'s
 * DISPATCH_COPIES is the same list, and `test_vdi_entry.py` holds the two equal). WS_CLIP is read once and
 * stored twice; LINEA_CUR_FONT is read BACK for the monospace flag rather than taken from the record.
 *
 * The record is held as the ROM holds it in A4, its base put on the bus once rather than each field's sum: the
 * two differ only for a record within WS_BYTES of the bus's top — the I/O page, which no open hands out. */
static void make_current(uint8_t *image, uint32_t work)
{
    const uint8_t *record = image + bus_dereference(work);
    uint16_t clip;

    wr32(image + LINEA_CUR_WORK, work);
    clip = be16(record + WS_CLIP);
    set_ram_word(image, LINEA_CLIP, clip);
    set_table_word(image, LINEA_INQ_TAB, VDI_INQ_TAB_CLIP_INDEX, clip);
    copy_field_word(image, LINEA_XMINCL, record, WS_XMN_CLIP);
    copy_field_word(image, LINEA_YMINCL, record, WS_YMN_CLIP);
    copy_field_word(image, LINEA_XMAXCL, record, WS_XMX_CLIP);
    copy_field_word(image, LINEA_YMAXCL, record, WS_YMX_CLIP);
    copy_field_word(image, LINEA_WRT_MODE, record, WS_WRT_MODE);
    copy_field_long(image, LINEA_PATPTR, record, WS_PATPTR);
    copy_field_word(image, LINEA_PATMSK, record, WS_PATMSK);
    set_ram_word(image, LINEA_MULTIFILL,
                 be16(record + WS_FILL_STYLE) == VDI_INTERIOR_USER ? be16(record + WS_MULTIFILL) : 0);
    copy_field_long(image, LINEA_FONT_RING + LINEA_FONT_RING_LOADED * VDI_LONG_BYTES, record, WS_LOADED_FONTS);
    copy_field_word(image, LINEA_DEV_TAB + VDI_DEV_TAB_FACES_INDEX * VDI_WORD_BYTES, record, WS_NUM_FONTS);
    copy_field_word(image, LINEA_DDA_INC, record, WS_DDA_INC);
    copy_field_word(image, LINEA_T_SCLSTS, record, WS_T_SCLSTS);
    copy_field_word(image, LINEA_SCALE, record, WS_SCALED);
    copy_field_long(image, LINEA_CUR_FONT, record, WS_CUR_FONT);
    set_ram_word(image, LINEA_MONO_STATUS,
                 font_word(image, be32(image + LINEA_CUR_FONT), FONT_FLAGS) & FONT_FLAG_MONOSPACE_MASK);
    copy_field_word(image, LINEA_SCRPT2, record, WS_SCRPT2);
    copy_field_long(image, LINEA_SCRTCHP, record, WS_SCRTCHP);
    copy_field_word(image, LINEA_STYLE, record, WS_STYLE);
    copy_field_word(image, VDI_TEXT_H_ALIGN, record, WS_H_ALIGN);
    copy_field_word(image, VDI_TEXT_V_ALIGN, record, WS_V_ALIGN);
    copy_field_word(image, LINEA_CHUP, record, WS_CHUP);
}

/* The function the opcode tables name, `jsr`ed: 1..39 and 100..131, compared SIGNED; any other opcode calls
 * nothing. The tables are ROM data, read where they lie. The call saves what it must round itself
 * (`call_vector_keeping`), so the lookups that call nothing do not pay for it. */
static void call_function(uint8_t *image, int16_t opcode)
{
    uint32_t table;
    int16_t first;

    if (opcode >= VDI_OPCODE_FIRST && opcode <= VDI_OPCODE_LAST) {
        table = VDI_OPCODE_TABLE;
        first = VDI_OPCODE_FIRST;
    } else if (opcode >= VDI_OPCODE_EXT_FIRST && opcode <= VDI_OPCODE_EXT_LAST) {
        table = VDI_OPCODE_TABLE_EXT;
        first = VDI_OPCODE_EXT_FIRST;
    } else {
        return;
    }
    call_vector_keeping(image, be32(image + table_entry(table, opcode - first, VDI_LONG_BYTES)));
}

/* $fca9f6 — the dispatcher. CONTRL is loaded once (`movea.l $299e,a5`); the handle and the opcode are read BEFORE
 * contrl[2] and contrl[4] are cleared. The two opens make their workstation, so they skip the lookup, and the
 * copies with it.
 *
 * contrl is held as the ROM holds it in A5, its base put on the bus once — `make_current`'s record, for the same
 * reason and at the same edge (a contrl within 14 bytes of the bus's top, the I/O page). Each field's own sum
 * costs the target an indexed mode per access (measured: `(d8,An,Dn.l)` for `d16(An)`), so this is the spelling. */
void vdi_dispatch(uint8_t *image)
{
    uint8_t *contrl = image + bus_dereference(linea_pointer(image, LINEA_CONTRL));
    int16_t handle = (int16_t)be16(contrl + CONTRL_HANDLE);
    int16_t opcode = (int16_t)be16(contrl + CONTRL_OPCODE);

    wr16(contrl + CONTRL_N_PTSOUT, 0);
    wr16(contrl + CONTRL_N_INTOUT, 0);
    set_ram_word(image, VDI_RESULT, 0);
    if (opcode != VDI_ROM_V_OPNWK_OPCODE && opcode != VDI_ROM_V_OPNVWK_OPCODE) {
        uint32_t work = workstation_with(image, handle);

        if (!work)
            return;
        make_current(image, work);
    }
    call_function(image, opcode);
}

/* $fc9f9e — the VDI's `trap #2` entry. The five pointers are read and stored in the block's order, contrl held
 * from its read (`movea.l (a0)+,a2`) and ptsin too (`movea.l (a0)+,a4`), whose place in Line-A the COPY takes.
 * The caller's point count is read after those stores; doubled in a WORD and capped UNSIGNED at the copy's
 * 1024 words — the cap written into the caller's own contrl[1] BEFORE the copy — and given back after the
 * dispatch through LINEA_CONTRL read afresh, which the function may have moved.
 *
 * contrl[1] is its own sum put on the bus (`2(a2)`); the block and the caller's points are walked from a base put
 * on the bus once (`(a0)+`, `(a4)+`), which parts from the 68000's per-access drive only for a block or a ptsin
 * within PB_BYTES or the copy's 2 KB of the bus's top — the I/O page, as `make_current` says of its record. */
TRANSCRIBED_CORE
uint16_t vdi_entry(uint8_t *image, uint32_t parameter_block)
{
    const uint8_t *block = image + bus_dereference(parameter_block);
    uint32_t contrl = be32(block + PB_CONTRL);
    uint32_t ptsin;
    uint8_t *points;
    uint16_t caller_points;

    wr32(image + LINEA_CONTRL, contrl);
    wr32(image + LINEA_INTIN, be32(block + PB_INTIN));
    ptsin = be32(block + PB_PTSIN);
    wr32(image + LINEA_PTSIN, VDI_PTSIN_COPY);
    wr32(image + LINEA_INTOUT, be32(block + PB_INTOUT));
    wr32(image + LINEA_PTSOUT, be32(block + PB_PTSOUT));
    points = image + bus_dereference(contrl + CONTRL_N_PTSIN);
    caller_points = be16(points);
    if (caller_points) {
        uint16_t words = (uint16_t)(caller_points + caller_points);

        if (words > VDI_PTSIN_COPY_WORDS) {
            words = VDI_PTSIN_COPY_WORDS;
            wr16(points, VDI_PTSIN_CAP_POINTS);
        }
        copy_words(image + VDI_PTSIN_COPY, image + bus_dereference(ptsin), words);
    }
    vdi_dispatch(image);
    set_contrl_word(image, CONTRL_N_PTSIN, caller_points);
    return be16(image + VDI_RESULT);
}
