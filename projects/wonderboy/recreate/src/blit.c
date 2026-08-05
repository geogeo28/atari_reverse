/* blit.c — the twelve masked planar sprite blitters at $8fce..$989c, which is every pixel the
 * sprite pass at $8f02 puts on the screen.
 *
 * ONE ALGORITHM, TWELVE ENTRY POINTS. Four widths (2..5 columns of 16 pixels) times three clip
 * cases (none, left edge, right edge), and every one of them is the same walk: read a source cell,
 * rotate its five words right as longwords by the sub-word shift, `and` the mask into the screen
 * and `or` the four planes over it, column by column, row by row. What separates the twelve is a
 * column COUNT, a clip mask and where the row ends. So this file is that walk once, plus a
 * `blit_width` per width and twelve one-line entry points — the same shape src/scroll.c's sixteen
 * unrolled copy variants took, and for the same reason: the original is one pattern unrolled by an
 * assembler, and thirteen hundred lines of transcription would hide the pattern rather than pin it.
 * test/test_blit.py is what makes that safe. It ASSEMBLES all 2254 bytes of the twelve from its own
 * statement of the same geometry and requires them to equal the shipped image, so a column count,
 * a threshold, a clip-mask value or a `lea` that is wrong here is wrong in bytes there too.
 *
 * THREE THINGS ARE REPRODUCED RATHER THAN TIDIED, all of them read off ../out/wonderboy_dis.txt:
 *
 *   * ONLY THE TWO-COLUMN BODIES COUNT THEIR ROWS UP FRONT. $9594 and $900a open with
 *     `addq.w #1,d7 / tst.w d7 / beq / bmi` and loop back to that test, so they refuse a row count
 *     that is zero or negative once bumped — and leave d7 at 0. The three wider widths just `dbf`,
 *     so an entry count of $ffff runs 65,537 rows there and they leave d7 at $ffff. Same interface,
 *     two behaviours, and `counts_rows_up_front` is which.
 *   * THE CLIPPED FOUR-COLUMN BODY MERGES ONE PLANE LATE. Every other body folds a cell's wrapped
 *     half into the next cell's word before testing whether the column is drawn; there the
 *     `or.w d4,d3` sits at $9324, INSIDE the arm the `btst` at $9312 branches to. Skipping the
 *     column therefore leaves that plane register unmerged. It changes no pixel — the low word it
 *     would have merged is only ever drawn by the arm that does merge it — but it changes the d3
 *     the routine returns, so it is `deferred_merge_column` here rather than a simplification.
 *   * THE ROW'S LAST `or.w` DOES NOT POST-INCREMENT, so a drawn row stops two bytes short of its own
 *     width and the `lea` that closes it is two larger than the arithmetic would suggest.
 *
 * WHAT THE ORIGINAL READS AND WRITES. In: a0 (source), a1 (screen), d6 (shift), d7 (rows), and for
 * a clip prelude d4 (screen x) plus a5 (the left ones' unwind). Out: the screen, WB_BLIT_CLIP_MASK
 * from a prelude, and d0..d5/d7/a0/a1 left wherever the last row put them. The width code the
 * dispatcher indexes its table by is in d2, which every body clobbers as scratch without reading —
 * the width is the entry point, not an argument.
 */
#include <stdint.h>

#include "blit.h"
#include "machine.h"
#include "os.h"
#include "wonderboy.h"

/* `move.l #$ffffffff,dn` before the mask word is moved into its low half — so this is what the
 * register holds ONCE that `move.w` has landed, which is what the rotate then acts on. (The
 * IMMEDIATE the instruction carries is all-ones; test/test_blit.py assembles the instruction and so
 * names that one, MASK_FILL_IMMEDIATE, while this names the register the pair leaves behind.) The
 * rotate brings these ones down into the bits the sprite does not cover, so the pixels either side
 * of it keep whatever the screen already held. The plane words are `clr.l`ed instead — nothing is
 * ORed in where the sprite is not. */
#define WB_BLIT_MASK_FILL         0xffff0000u

/* The number of BITS the rotate must turn a longword by to bring its high half down: 68k `swap`. */
#define WB_BLIT_SWAP_BITS         16u

/* `deferred_merge_column` for the three widths whose clipped bodies have no such quirk. */
#define WB_BLIT_NO_DEFERRED_MERGE 0xffu

/* `blit_sprite_rows`' own argument: whether the body tests WB_BLIT_CLIP_MASK per column at all. The
 * four table_mid entries do not, and never read the byte; the eight preludes reach the same body
 * with it on, having just written it. */
#define WB_BLIT_UNCLIPPED         0
#define WB_BLIT_CLIPPED           1

/* One width, which is one entry in each of the three jump tables. */
typedef struct {
    unsigned columns;                /* 16-pixel columns per row; cells per row is one fewer */
    uint16_t row_advance;            /* the `lea N(a1),a1` that closes a row */
    int counts_rows_up_front;        /* the `addq.w #1,d7 / tst / beq / bmi` only $9594/$900a have */
    unsigned deferred_merge_column;  /* the clipped body's late `or.w`; see the file comment */
} blit_width;

/* One row of that table. Everything but the quirk follows from the column count, so the width
 * number is written once per width and the two derivations are stated once for all four. */
#define BLIT_WIDTH(n, deferred) {                                    \
    .columns = (n),                                                  \
    .row_advance = WB_BLIT_ROW_ADVANCE(n),                           \
    .counts_rows_up_front = (n) == WB_BLIT_GUARDED_COLUMNS,          \
    .deferred_merge_column = (deferred),                             \
}

static const blit_width BLIT_W2 = BLIT_WIDTH(2, WB_BLIT_NO_DEFERRED_MERGE);
static const blit_width BLIT_W3 = BLIT_WIDTH(3, WB_BLIT_NO_DEFERRED_MERGE);
static const blit_width BLIT_W4 = BLIT_WIDTH(4, WB_BLIT_DEFERRED_MERGE_COLUMN);
static const blit_width BLIT_W5 = BLIT_WIDTH(5, WB_BLIT_NO_DEFERRED_MERGE);

/* 68k `ror.l Dm,Dn`, as the kit's `rotate_left32` mirrored — a 32-bit rotate is cyclic, so rotating
 * right by n is rotating left by 32-n, and rotate_left32's own `& 31` makes a count of 0 the
 * 68000's no-op rather than C's undefined `value >> 32`. Exact for every count a register can hold:
 * the 68000 rotates by Dm mod 64, and mod 64 then mod 32 is mod 32. */
static uint32_t rotate_right32(uint32_t value, unsigned count)
{
    return rotate_left32(value, 32u - (count & 31u));
}

/* 68k `swap Dn`: the half the rotate pushed out of this column comes down into the low word, which
 * is where the next column is drawn from. A rotate by half a longword IS the swap, so it is that
 * one operation (machine.h's) rather than a second shuffle of its own. */
static uint32_t swap_halves(uint32_t value)
{
    return rotate_left32(value, WB_BLIT_SWAP_BITS);
}

/* One word of the image, addressed THE WAY THE ORACLE'S BUS DOES.
 *
 * `source` and `dest` are entry registers: the caller hands them addresses and nothing bounds
 * either, so a wrong one is not a wrong pixel but a walk off the end of the image — into the host
 * heap here, where the 68000 side merely reaches an address the shim does not map. The shim answers
 * a read past the image with zeros and DROPS the write (tools/recreate_kit/oracle/shim.c), so that
 * is what these do, and an insane address then diverges nowhere rather than corrupting the test
 * process. Every address inside the image goes through unchanged, which is what the battery pins —
 * this is the divergence class src/rad.c's comment registers, closed for this family because the
 * runaway `dbf` below can walk 10 MB of screen from one bad row count. */
static uint16_t blit_read_word(const uint8_t *image, uint32_t addr)
{
    return os_in_image(addr, WB_STATE_WORD_LEN) ? be16(image + addr) : 0;
}

static void blit_write_word(uint8_t *image, uint32_t addr, uint16_t value)
{
    if (os_in_image(addr, WB_STATE_WORD_LEN))
        wr16(image + addr, value);
}

/* Which of d0..d5 holds cell `cell`'s mask — d1, d0, d5, d4 for cells 0..3. The original steps the
 * window DOWN one register per cell so that the cell it is loading never overwrites the one it is
 * still merging from. */
static unsigned mask_reg(unsigned cell)
{
    return (WB_BLIT_SCRATCH_REGS + 1u - cell) % WB_BLIT_SCRATCH_REGS;
}

/* ...and the four planes, which follow the mask upward through the same window. `plane` is 0-based,
 * so the four words of a cell after its mask are plane_reg(cell, 0..WB_PLANES-1). */
static unsigned plane_reg(unsigned cell, unsigned plane)
{
    return (mask_reg(cell) + 1u + plane) % WB_BLIT_SCRATCH_REGS;
}

/* `btst #n,WB_BLIT_CLIP_MASK`: the LEFTMOST column is the HIGHEST bit, so a mask of 1 draws the
 * rightmost column alone and one of all-ones draws every column. */
static unsigned column_bit(const blit_width *width, unsigned column)
{
    return 1u << (width->columns - 1u - column);
}

/* Folding the previous cell's wrapped half into the word just loaded: `and.w Dw,Dr` for a mask and
 * `or.w Dw,Dr` for one of the four planes. A WORD op either way, so the freshly loaded word's own
 * high half — the part that will wrap into the column after this one — survives untouched. Two
 * functions rather than one with a flag, because they are two instructions and the deferred fold
 * below is only ever the `or.w`. */
static uint32_t and_wrapped_half(uint32_t loaded, uint32_t wrapped)
{
    return set_low_word(loaded, (uint16_t)(loaded & wrapped));
}

static uint32_t or_wrapped_half(uint32_t loaded, uint32_t wrapped)
{
    return set_low_word(loaded, (uint16_t)(loaded | wrapped));
}

/* Read one source cell into the register window, rotating each of its WB_BLIT_CELL_WORDS words.
 *
 * Every cell after the first also SWAPS the previous cell's register as it goes, exposing the half
 * the rotate pushed past the 16-pixel boundary, and folds that half into the word just loaded. That
 * fold is the seam between two columns, and it is why the source is read UNCONDITIONALLY even in a
 * clipped body: a skipped column still owes the next one its wrapped half.
 *
 * `defer_last_merge` holds the FOURTH plane's fold back for the caller to do inside the drawn arm
 * of its `btst` — the four-column clipped body's quirk, and nothing else's.
 */
static void blit_load_cell(const uint8_t *image, sprite_blit_regs *regs, unsigned cell,
                           int defer_last_merge)
{
    for (unsigned word = 0; word < WB_BLIT_CELL_WORDS; word++) {
        /* The cell's five words are the mask and then the four planes, in that order. */
        int is_mask = (word == 0);
        unsigned reg = is_mask ? mask_reg(cell) : plane_reg(cell, word - 1);
        uint32_t loaded = rotate_right32(
            (is_mask ? WB_BLIT_MASK_FILL : 0u) | blit_read_word(image, regs->source), regs->shift);

        regs->source = addr_add(regs->source, WB_STATE_WORD_LEN);
        if (cell == 0) {
            regs->scratch[reg] = loaded;
            continue;
        }

        unsigned wrapped = is_mask ? mask_reg(cell - 1) : plane_reg(cell - 1, word - 1);
        int hold_back = defer_last_merge && word == WB_BLIT_CELL_WORDS - 1;

        regs->scratch[wrapped] = swap_halves(regs->scratch[wrapped]);
        regs->scratch[reg] = hold_back ? loaded
                           : is_mask   ? and_wrapped_half(loaded, regs->scratch[wrapped])
                                       : or_wrapped_half(loaded, regs->scratch[wrapped]);
    }
}

/* The row's LAST column is the last cell's wrapped half on its own, so all five of that cell's
 * registers are swapped and drawn from as they stand. */
static void blit_swap_cell(sprite_blit_regs *regs, unsigned cell)
{
    regs->scratch[mask_reg(cell)] = swap_halves(regs->scratch[mask_reg(cell)]);
    for (unsigned plane = 0; plane < WB_PLANES; plane++)
        regs->scratch[plane_reg(cell, plane)] = swap_halves(regs->scratch[plane_reg(cell, plane)]);
}

/* One 16-pixel column: `and.w mask,(a1) / or.w plane,(a1)+` per plane, the last of them without the
 * post-increment. The original spells the read-modify-write as two stores to the same word; one
 * store of the same value leaves the same byte and the same write set. */
static void blit_column(uint8_t *image, sprite_blit_regs *regs, unsigned cell, int is_last)
{
    uint16_t mask = (uint16_t)regs->scratch[mask_reg(cell)];

    for (unsigned plane = 0; plane < WB_PLANES; plane++) {
        uint16_t under = blit_read_word(image, regs->dest);
        uint16_t plane_word = (uint16_t)regs->scratch[plane_reg(cell, plane)];

        blit_write_word(image, regs->dest, (uint16_t)((under & mask) | plane_word));
        if (!(is_last && plane == WB_PLANES - 1))
            regs->dest = addr_add(regs->dest, WB_STATE_WORD_LEN);
    }
}

/* One row of the sprite: `columns` columns drawn from `columns - 1` source cells, then the `lea`
 * that steps the screen cursor to the next scanline. In a clipped body a column whose bit is clear
 * is stepped over instead of drawn, at the same cost, so this closes at the same place either way.
 */
static void blit_row(uint8_t *image, sprite_blit_regs *regs, const blit_width *width, int clipped)
{
    unsigned cells = width->columns - 1u;

    for (unsigned column = 0; column < width->columns; column++) {
        int is_last = (column == cells);
        unsigned cell = is_last ? cells - 1u : column;
        int defer = clipped && column == width->deferred_merge_column;

        if (is_last)
            blit_swap_cell(regs, cell);
        else
            blit_load_cell(image, regs, cell, defer);

        if (clipped && !(image[WB_BLIT_CLIP_MASK] & column_bit(width, column))) {
            regs->dest = addr_add(regs->dest, is_last ? WB_BLIT_LAST_COLUMN_BYTES
                                                      : WB_BLIT_COLUMN_BYTES);
            continue;
        }
        if (defer) {
            /* $9324's `or.w d4,d3`: the fold blit_load_cell held back, done here INSIDE the arm
             * that draws — it is a plane's, never a mask's. */
            unsigned last_plane = WB_PLANES - 1u;
            regs->scratch[plane_reg(cell, last_plane)] = or_wrapped_half(
                regs->scratch[plane_reg(cell, last_plane)],
                regs->scratch[plane_reg(cell - 1u, last_plane)]);
        }
        blit_column(image, regs, cell, is_last);
    }
    regs->dest = addr_add(regs->dest, width->row_advance);
}

/* The whole blit: one row per pass of whichever of the two loop shapes this width uses. */
static void blit_sprite_rows(uint8_t *image, sprite_blit_regs *regs, const blit_width *width,
                             int clipped)
{
    if (width->counts_rows_up_front) {
        /* `addq.w #1,d7`, ONCE — the `dbf` at the bottom jumps back to the `tst.w d7` below it,
         * not to the bump. The `beq` and the `bmi` between them refuse every count that is not
         * positive, so the `dbf` on this path always branches and the loop always exits on the
         * `beq` with the counter at zero. */
        regs->rows = set_low_word(regs->rows, (uint16_t)(regs->rows + 1u));
        while ((int16_t)(uint16_t)regs->rows > 0) {
            blit_row(image, regs, width, clipped);
            regs->rows = set_low_word(regs->rows, (uint16_t)(regs->rows - 1u));
        }
        return;
    }
    /* `dbf d7,<top>` alone: the row is drawn BEFORE the count is looked at, so `rows` is a
     * "one fewer than this many" and an entry value of $ffff draws 65,537 rows rather than none.
     * Reproduced by construction and left unreached — see test/test_blit.py. */
    do {
        blit_row(image, regs, width, clipped);
        regs->rows = set_low_word(regs->rows, (uint16_t)(regs->rows - 1u));
    } while ((uint16_t)regs->rows != (uint16_t)-1);
}

/* The screen x a prelude clips against: d4's low word, SIGNED — every threshold is compared with a
 * `blt`/`bge`, and the left-hand ones are negative. */
static int16_t clip_x(const sprite_blit_regs *regs)
{
    return (int16_t)(uint16_t)regs->scratch[WB_BLIT_X_REG];
}

/* The four LEFT preludes. Arm k (k = 1 upward) fires at an x of -16k or above and drops the k
 * leftmost columns, leaving the low `columns - k` bits of the clip mask set. Past the last arm not
 * one column is on screen: nothing is drawn, and `unwind` — a5, which no other arm of this family
 * touches — is stepped back by WB_BLIT_UNWIND_BYTES. */
static void blit_clip_left(uint8_t *image, sprite_blit_regs *regs, const blit_width *width)
{
    for (unsigned dropped = 1; dropped < width->columns; dropped++) {
        if (clip_x(regs) >= -(int16_t)(WB_BLIT_COLUMN_PIXELS * dropped)) {
            image[WB_BLIT_CLIP_MASK] = (uint8_t)((1u << (width->columns - dropped)) - 1u);
            blit_sprite_rows(image, regs, width, WB_BLIT_CLIPPED);
            return;
        }
    }
    regs->unwind = addr_add(regs->unwind, (uint32_t)-WB_BLIT_UNWIND_BYTES);
}

/* The four RIGHT preludes, the same ladder from the other end. Arm k (k = 0 upward) fires below an
 * x of WB_BLIT_SCREEN_EDGE_X - 16 * (columns - k) and drops the k RIGHTMOST columns. Past the last
 * arm the whole sprite is off the right edge and the routine returns having touched nothing —
 * no clip mask, no unwind. */
static void blit_clip_right(uint8_t *image, sprite_blit_regs *regs, const blit_width *width)
{
    unsigned all_columns = (1u << width->columns) - 1u;

    for (unsigned dropped = 0; dropped < width->columns; dropped++) {
        int16_t threshold = (int16_t)(WB_BLIT_SCREEN_EDGE_X
                                      - WB_BLIT_COLUMN_PIXELS * (width->columns - dropped));
        if (clip_x(regs) < threshold) {
            image[WB_BLIT_CLIP_MASK] = (uint8_t)(all_columns & ~((1u << dropped) - 1u));
            blit_sprite_rows(image, regs, width, WB_BLIT_CLIPPED);
            return;
        }
    }
}

/* --- the twelve entry points --------------------------------------------------------------------- */

void blit_sprite_w2(uint8_t *image, sprite_blit_regs *regs)
{
    blit_sprite_rows(image, regs, &BLIT_W2, WB_BLIT_UNCLIPPED);
}

void blit_sprite_w3(uint8_t *image, sprite_blit_regs *regs)
{
    blit_sprite_rows(image, regs, &BLIT_W3, WB_BLIT_UNCLIPPED);
}

void blit_sprite_w4(uint8_t *image, sprite_blit_regs *regs)
{
    blit_sprite_rows(image, regs, &BLIT_W4, WB_BLIT_UNCLIPPED);
}

void blit_sprite_w5(uint8_t *image, sprite_blit_regs *regs)
{
    blit_sprite_rows(image, regs, &BLIT_W5, WB_BLIT_UNCLIPPED);
}


void blit_clip_left_w2(uint8_t *image, sprite_blit_regs *regs)
{
    blit_clip_left(image, regs, &BLIT_W2);
}

void blit_clip_left_w3(uint8_t *image, sprite_blit_regs *regs)
{
    blit_clip_left(image, regs, &BLIT_W3);
}

void blit_clip_left_w4(uint8_t *image, sprite_blit_regs *regs)
{
    blit_clip_left(image, regs, &BLIT_W4);
}

void blit_clip_left_w5(uint8_t *image, sprite_blit_regs *regs)
{
    blit_clip_left(image, regs, &BLIT_W5);
}

void blit_clip_right_w2(uint8_t *image, sprite_blit_regs *regs)
{
    blit_clip_right(image, regs, &BLIT_W2);
}

void blit_clip_right_w3(uint8_t *image, sprite_blit_regs *regs)
{
    blit_clip_right(image, regs, &BLIT_W3);
}

void blit_clip_right_w4(uint8_t *image, sprite_blit_regs *regs)
{
    blit_clip_right(image, regs, &BLIT_W4);
}

void blit_clip_right_w5(uint8_t *image, sprite_blit_regs *regs)
{
    blit_clip_right(image, regs, &BLIT_W5);
}
