/* video.c — the screen buffers, the shifter sink, and the block clears/copies around them.
 *
 * Five of the six routines here are plain image-to-image work: three clears sized in whole
 * buffers (`screen_clear`, `clear_backdrop_page0`, `playfield_clear`) and one strip copy
 * (`blit_graphic_block`) that the front-end screens are assembled out of. The other two —
 * `screen_flip_buffers` and `set_palette_title` — end at the video shifter, which is not an image
 * byte; include/video.h's header comment says what that costs and what the sink recovers.
 */
#include <string.h>

#include "machine.h"
#include "video.h"

/* ================================================================================================
 * THE SHIFTER SINK. Off target a write to $ff8201/$ff8203/$ff8240 goes nowhere — there is no such
 * address in the differential's image, and dereferencing one from the .so would be a wild pointer —
 * so the sink records the payload instead and the glue hands that record to the diff. What the
 * record buys over recomputing the payload in the glue is that the CORE's own loop is what fills it:
 * a candidate uploading seven colour longs instead of eight leaves the eighth slot at zero, which no
 * upload the original makes produces.
 *
 * Cleared by the glue before each call rather than accumulated, so one case's writes can never stand
 * in for the next one's.
 * ============================================================================================= */
static uint32_t g_palette_written[SHIFTER_PALETTE_PAIRS];
static uint8_t g_screen_base_written[2];       /* the $ff8203 byte, then the $ff8201 byte */

/* Indexed by the colour register pair rather than appended, because the index IS the destination on
 * the hardware: a core that uploaded the row short leaves the later slots at zero, which is not any
 * colour the original wrote. */
void shifter_palette_write(unsigned pair, uint32_t colours) {
    if (pair < SHIFTER_PALETTE_PAIRS)
        g_palette_written[pair] = colours;
}

void shifter_screen_base_write(uint8_t mid, uint8_t high) {
    g_screen_base_written[0] = mid;
    g_screen_base_written[1] = high;
}

/* The sink's one reset, so the "cleared before the call" discipline is a function a new shifter
 * routine's glue calls rather than a `memset` each glue has to remember. A glue that forgot it
 * would compare the PREVIOUS case's record and report green over an upload it never made. */
static void shifter_sink_reset(void) {
    memset(g_palette_written, 0, sizeof g_palette_written);
    memset(g_screen_base_written, 0, sizeof g_screen_base_written);
}

/* One `clr.l (a0)+` run. Three routines here zero a whole buffer and differ only in where and how
 * much; the ONE thing they must agree on is that the cursor steps the way the 68000's address ALU
 * does (machine.h's `addr_add`), which is what makes this a helper rather than three loops. Its
 * twin on the copying side is `copy_longs` in src/scroll.c.
 *
 * `first` is the LOWEST address written and the run ascends from it; `playfield_clear` descends
 * instead, and its own comment says why that is not observable. */
static void zero_longs(uint8_t *image, uint32_t first, unsigned bytes) {
    for (unsigned offset = 0; offset < bytes; offset += 4)
        wr32(image + addr_add(first, offset), 0);
}

/* ================================================================================================
 * screen_clear @ 0x1296e — 2 call sites (0x12a36, 0x13346), both front-end screens.
 *
 * `move.w #$1f3f,d0 / clr.l (a0)+ / dbf d0`: 8000 longwords, a whole 320x200 four-plane frame.
 * ============================================================================================= */
void screen_clear(uint8_t *image, uint32_t buffer) {
    zero_longs(image, buffer, SCREEN_BYTES);
}

/* ================================================================================================
 * clear_backdrop_page0 @ 0x12fc2 — 1 call site (0x12eae), inside the front end's compose step.
 *
 * `move.w #$167f,d7`: 5760 longwords = one playfield's worth, at the fixed backdrop page.
 * ============================================================================================= */
void clear_backdrop_page0(uint8_t *image) {
    zero_longs(image, A_backdrop_page0, PLAYFIELD_BYTES);
}

/* ================================================================================================
 * playfield_clear @ 0x1597c — 3 call sites (0x11196, 0x12e66, 0x1342a), the
 * scroller's "no background this frame" path.
 *
 * It zeroes the same 23040 bytes the two above do, but DOWNWARDS from the end of the playfield and
 * through `movem.l #$7ff8,-(a6)` — twelve registers (a4..a0, d7..d1) the prologue has just set to
 * zero, four bursts to a pass, 192 bytes a pass, 120 passes. THE DIRECTION IS NOT OBSERVABLE and so
 * is not transcribed: every byte written is zero and no two writes overlap, so an ascending run
 * leaves the same image. It is `zero_longs` like its two neighbours, and this comment is where the
 * predecrement burst is recorded for the port that will want it back.
 * ============================================================================================= */
void playfield_clear(uint8_t *image) {
    zero_longs(image, be32(image + A_screen_back), PLAYFIELD_BYTES);
}

/* ================================================================================================
 * blit_graphic_block @ 0x134b8 — 11 call sites, all in the two front-end screen builders.
 *
 * One `movem.l (a6)+,#$02fe` / `movem.l #$02fe,(a0)` pair a row: eight longwords through d1-d7 and
 * a1, which is 32 pixels of a four-plane ST row. The source runs straight on; the destination steps
 * a whole screen row, so the block is a 32-pixel-wide column strip.
 *
 * `last_row` is D0 as the caller loads it — a `dbf` count, so the block is `last_row + 1` rows tall.
 *
 * THE WHOLE ROW IS READ BEFORE ANY OF IT IS STORED, because a `movem` pair is two instructions and
 * not eight interleaved copies. That is observable the moment the two strips overlap, which
 * test_video.py's `test_blit_graphic_block_overlapping` drives: at dst = src + 2 an interleaved
 * reconstruction reads back its own stores from the third longword on (measured — that case is what
 * caught it).
 * ============================================================================================= */
#define GRAPHIC_BLOCK_ROW_LONGS (GRAPHIC_BLOCK_ROW_BYTES / 4u)

void blit_graphic_block(uint8_t *image, uint32_t src, uint32_t dst, uint16_t last_row) {
    unsigned rows = loop_passes((uint16_t)(last_row + 1u), COUNT_MASK_WORD);

    for (unsigned row = 0; row < rows; row++) {
        uint32_t held[GRAPHIC_BLOCK_ROW_LONGS];      /* d1-d7 and a1, the movem's register set */

        for (unsigned i = 0; i < GRAPHIC_BLOCK_ROW_LONGS; i++)
            held[i] = be32(image + addr_add(src, 4u * i));
        for (unsigned i = 0; i < GRAPHIC_BLOCK_ROW_LONGS; i++)
            wr32(image + addr_add(dst, 4u * i), held[i]);
        src = addr_add(src, GRAPHIC_BLOCK_ROW_BYTES);
        dst = addr_add(dst, SCREEN_ROW_BYTES);
    }
}

/* ================================================================================================
 * screen_flip_buffers @ 0x1297a — 10 call sites, every screen the game presents.
 *
 * Swaps the two framebuffer pointers and then publishes the one that has just become the FRONT
 * buffer to the shifter, as the two bytes the hardware takes. Half of that is an ordinary image
 * write the differential compares; the publish is the sink's (include/video.h).
 * ============================================================================================= */
void screen_flip_buffers(uint8_t *image) {
    uint32_t was_back = be32(image + A_screen_back);
    uint32_t was_front = be32(image + A_screen_front);

    wr32(image + A_screen_back, was_front);
    wr32(image + A_screen_front, was_back);
    /* `move.l $17982.l,d0` re-reads screen_front AFTER the swap, so the address published is the
     * buffer just drawn into. `lsr.l #8` then `move.b d0,$ff8203`, `lsr.l #8` then `$ff8201`. */
    shifter_screen_base_write((uint8_t)(was_back >> 8), (uint8_t)(was_back >> 16));
}

/* ================================================================================================
 * set_palette_title @ 0x153ae — 1 call site (0x10084, `_start`, right after the first flip).
 *
 * `movem.l $19618.l,#$00ff / movem.l #$00ff,$ff8240.l`: the whole sixteen-colour row in one go,
 * through d0-d7, with no fade and no per-pen arithmetic. Reading it as longwords rather than as
 * sixteen colours is the original's own width, and it is what makes the load and the store one
 * movem each.
 * ============================================================================================= */
void set_palette_title(uint8_t *image) {
    for (unsigned pair = 0; pair < SHIFTER_PALETTE_PAIRS; pair++)
        shifter_palette_write(pair, be32(image + A_palette_boot + 4u * pair));
}

/* ================================================================================================
 * Glue.
 *
 * Register map: `screen_clear` A0 = buffer; `blit_graphic_block` A6 = source, A0 = destination,
 * D0 = last row index. The other four take no arguments — their addresses are all absolute.
 *
 * The two shifter routines' glue publishes the sink's record at `result`, where the oracle's stub
 * has stored the same registers the original hands the hardware (test/abi.py). Both call the core
 * and copy what IT wrote rather than recomputing the payload, so a mutation inside the core — a
 * short upload, the wrong base, the two base bytes swapped — is caught rather than mirrored.
 * ============================================================================================= */
void g_screen_clear(uint8_t *image, uint32_t buffer) {
    screen_clear(image, buffer);
}

void g_clear_backdrop_page0(uint8_t *image) {
    clear_backdrop_page0(image);
}

void g_playfield_clear(uint8_t *image) {
    playfield_clear(image);
}

void g_blit_graphic_block(uint8_t *image, uint32_t src, uint32_t dst, uint32_t last_row) {
    blit_graphic_block(image, src, dst, (uint16_t)last_row);
}

/* The two published bytes as one word, high byte first, for the test to compare against the
 * ORACLE'S OWN registers: `screen_flip_buffers` leaves A0 holding the buffer it published and D0
 * holding that address shifted down 16, so both halves of the pair have an oracle-side witness even
 * though neither write lands in the image. A candidate that never called the sink returns 0, which
 * no real buffer address produces. Returned rather than stored: it is two bytes of answer, and an
 * image write would need a scratch address the routine itself has nothing to do with. */
uint32_t g_screen_flip_buffers(uint8_t *image) {
    shifter_sink_reset();
    screen_flip_buffers(image);

    return (uint32_t)((g_screen_base_written[1] << 8) | g_screen_base_written[0]);
}

/* `result` is where test/abi.py's stub stored the oracle's d0-d7 — the eight longwords the original
 * hands $ff8240 — so publishing the sink's record there puts both sides' upload in the image diff. */
void g_set_palette_title(uint8_t *image, uint32_t result) {
    shifter_sink_reset();
    set_palette_title(image);

    for (unsigned pair = 0; pair < SHIFTER_PALETTE_PAIRS; pair++)
        wr32(image + result + 4u * pair, g_palette_written[pair]);
}
