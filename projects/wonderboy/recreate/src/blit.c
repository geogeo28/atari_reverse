/* blit.c — the SPRITE TIER, end to end: the pass at $8f02 that walks the screen records and the
 * twelve masked planar sprite blitters at $8fce..$989c it dispatches to, which between them are
 * every sprite pixel the game puts on the screen. The pass is at the bottom of this file.
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
 *     so an entry count of $ffff runs the WHOLE 16-BIT RANGE of them there — 65,536 rows, not the
 *     65,537 batch 14 stated — and they leave d7 at $ffff. The exit condition is the `dbf`'s own:
 *     the counter has been decremented once per row and is back at $ffff. Same interface, two
 *     behaviours, and `counts_rows_up_front` is which. THE PASS BELOW REACHES THAT COUNT: a
 *     descriptor whose height byte is negative and whose y is inside the band comes out of the
 *     bottom clamp still negative, so the runaway is reachable BY DATA and is pinned as such
 *     (`test_a_negative_height_runs_a_wider_body_away`).
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

/* `blit_sprite_rows_body`'s own argument: whether the body tests WB_BLIT_CLIP_MASK per column at
 * all. The four table_mid entries do not, and never read the byte; the eight preludes reach the
 * same walk with it on, having just written it. */
#define WB_BLIT_UNCLIPPED         0
#define WB_BLIT_CLIPPED           1

/* The axis the two row walks below are specialised on, and the argument every access helper they
 * inline carries: WB_BLIT_ROW_IN_IMAGE for a row blit_row has PROVED lies wholly inside the image,
 * WB_BLIT_ROW_CHECKED for one it has not. See blit_row. */
#define WB_BLIT_ROW_IN_IMAGE      1
#define WB_BLIT_ROW_CHECKED       0

/* One width, which is one entry in each of the three jump tables. */
typedef struct {
    unsigned columns;                /* 16-pixel columns per row; cells per row is one fewer */
    uint16_t row_advance;            /* the `lea N(a1),a1` that closes a row */
    uint32_t source_bytes;           /* what one row reads from a0, and what one writes from a1 —
                                      * blit.h's row-geometry section derives both and pins the
                                      * second against row_advance. They are per WIDTH, so they are
                                      * table entries rather than a computation per row. */
    uint32_t dest_bytes;
    int counts_rows_up_front;        /* the `addq.w #1,d7 / tst / beq / bmi` only $9594/$900a have */
    unsigned deferred_merge_column;  /* the clipped body's late `or.w`; see the file comment */
} blit_width;

/* One row of that table. Everything but the quirk follows from the column count, so the width
 * number is written once per width and the derivations are stated once for all four. */
#define BLIT_WIDTH(n, deferred) {                                    \
    .columns = (n),                                                  \
    .row_advance = WB_BLIT_ROW_ADVANCE(n),                           \
    .source_bytes = WB_BLIT_ROW_SOURCE_BYTES(n),                     \
    .dest_bytes = WB_BLIT_ROW_DEST_BYTES(n),                         \
    .counts_rows_up_front = (n) == WB_BLIT_GUARDED_COLUMNS,          \
    .deferred_merge_column = (deferred),                             \
}

static const blit_width BLIT_W2 = BLIT_WIDTH(2, WB_BLIT_NO_DEFERRED_MERGE);
static const blit_width BLIT_W3 = BLIT_WIDTH(3, WB_BLIT_NO_DEFERRED_MERGE);
static const blit_width BLIT_W4 = BLIT_WIDTH(4, WB_BLIT_DEFERRED_MERGE_COLUMN);
static const blit_width BLIT_W5 = BLIT_WIDTH(5, WB_BLIT_NO_DEFERRED_MERGE);

/* THE COUNT EVERY ROTATE OF ONE BLIT TURNS BY, taken apart ONCE FOR THE WHOLE BLIT rather than once
 * per word. `shift` is d6, and nothing in this family writes it — not a row, not a column, not a
 * prelude — so the reduction is invariant over every row the entry count draws, and
 * blit_sprite_rows_body computes it before its first row and hands it down. The five bits are exact
 * for every count a register can hold, for the kit's rotate_right32's own reason: the 68000 rotates
 * by Dm mod 64 and a 32-bit rotate is cyclic mod 32, and mod 64 then mod 32 is mod 32. Doing it here
 * leaves the rotate's own `& 31` a fold rather than an instruction. */
static unsigned blit_rotation(const sprite_blit_regs *regs)
{
    return regs->shift & 31u;
}

/* 68k `swap Dn`: the half the rotate pushed out of this column comes down into the low word, which
 * is where the next column is drawn from. A rotate by half a longword IS the swap, so it is that
 * one operation (machine.h's) rather than a second shuffle of its own. */
static uint32_t swap_halves(uint32_t value)
{
    return rotate_left32(value, WB_BLIT_SWAP_BITS);
}

/* One word of the image, addressed THE WAY THE ORACLE'S BUS DOES — ON THE ARM THAT HAS TO ASK.
 *
 * `source` and `dest` are entry registers: the caller hands them addresses and nothing bounds
 * either, so a wrong one is not a wrong pixel but a walk off the end of the image — into the host
 * heap here, where the 68000 side merely reaches an address the shim does not map. The shim answers
 * a read past the image with zeros and DROPS the write (tools/recreate_kit/oracle/shim.c), so that
 * is what the CHECKED arm of each of these does, and an insane address then diverges nowhere rather
 * than corrupting the test process. Every address inside the image goes through unchanged, which is
 * what the battery pins — this is the divergence class src/rad.c's comment registers, closed for
 * this family because the runaway `dbf` below can walk 10 MB of screen from one bad row count.
 *
 * The OTHER arm asks nothing, and is the same answer rather than a weaker one: `row_in_image` is
 * WB_BLIT_ROW_IN_IMAGE only for a row blit_row has PROVED lies wholly inside the image, where the
 * guard could only ever say yes. It is a COMPILE-TIME CONSTANT in both of the walks below — that is
 * what the two instantiations there are for — so each of them keeps one arm of these and no test.
 * Which arm a given row takes is therefore blit_row's decision alone, and the two spans it decides
 * on are blit.h's. */

/* The kit's own `os_in_image` for the ONE width this file ever asks it about — a screen word — in
 * its constant-width form, which is the SAME predicate as a single comparison. os.h states the
 * collapse and the wrap-safety argument behind it once, where the two forms are defined together, so
 * this is a name for that call and not a second derivation of it.
 *
 * WHY THE ONE COMPARISON IS WORTH ASKING FOR HERE. This is the guard on every word of the CHECKED
 * walk, which is inlined once per width and clip case, and each comparison the two-clause form keeps
 * is a branch the two walks around it get duplicated through — thousands of bytes of text over the
 * twelve entry points, for a walk no drawn sprite ever takes (measured; see ../STATUS.md,
 * "## Performance"). The surface that would catch a version of this that is one word too generous is
 * `make guarded`, where the image's surroundings are PROT_NONE and a read past the end faults rather
 * than differing. The boundary itself is pinned against the oracle's bus by test/test_blit.py's
 * `test_a_row_reaching_the_end_of_the_image_drops_the_word_that_falls_off` and its reading twin. */
static inline __attribute__((always_inline))
int blit_word_in_image(uint32_t addr)
{
    return os_in_image_fixed(addr, WB_STATE_WORD_LEN);
}

static inline __attribute__((always_inline))
uint16_t blit_read_word(const uint8_t *image, uint32_t addr, int row_in_image)
{
    if (row_in_image)
        return be16(image + addr);
    return blit_word_in_image(addr) ? be16(image + addr) : 0;
}

static inline __attribute__((always_inline))
void blit_write_word(uint8_t *image, uint32_t addr, uint16_t value, int row_in_image)
{
    if (row_in_image) {
        wr16(image + addr, value);
        return;
    }
    if (blit_word_in_image(addr))
        wr16(image + addr, value);
}

/* Which of d0..d5 holds cell `cell`'s mask — d1, d0, d5, d4 for cells 0..3. The original steps the
 * window DOWN one register per cell so that the cell it is loading never overwrites the one it is
 * still merging from.
 *
 * Both helpers wrote that walk as a `%` until the profiler read the row loop: the 68000 has no
 * 32-bit divide, so every `%` was a libgcc call — 856 of them a frame. What lets a conditional
 * subtract stand in for it is that the callers keep each sum within ONE window of the wrap point:
 * cell <= WB_BLIT_COLUMNS_MAX - 2 (blit_row draws cells = columns - 1, for columns 2..5) and
 * plane <= WB_PLANES - 1, so plane_reg's sum is at most
 * (WB_BLIT_SCRATCH_REGS - 1) + 1 + (WB_PLANES - 1) = 9 < 2 * WB_BLIT_SCRATCH_REGS. */
_Static_assert(WB_BLIT_CELL_WORDS == WB_PLANES + 1u,
               "blit_load_cell passes word - 1 as plane for word < WB_BLIT_CELL_WORDS, so the plane "
               "bound above holds only while a cell is one mask word followed by WB_PLANES planes");

static unsigned mask_reg(unsigned cell)
{
    unsigned reg = WB_BLIT_SCRATCH_REGS + 1u - cell;

    return reg < WB_BLIT_SCRATCH_REGS ? reg : reg - WB_BLIT_SCRATCH_REGS;
}

/* ...and the four planes, which follow the mask upward through the same window. `plane` is 0-based,
 * so the four words of a cell after its mask are plane_reg(cell, 0..WB_PLANES-1). */
static unsigned plane_reg(unsigned cell, unsigned plane)
{
    unsigned reg = mask_reg(cell) + 1u + plane;

    return reg < WB_BLIT_SCRATCH_REGS ? reg : reg - WB_BLIT_SCRATCH_REGS;
}

/* THE WHOLE WINDOW WALK IS THIS ONE STEP. A cell's WB_BLIT_CELL_WORDS words land in consecutive
 * registers from mask_reg(cell) upward — that is plane_reg's `mask_reg + 1 + plane` — and the
 * window steps DOWN one register per cell, so mask_reg(cell - 1) is mask_reg(cell) + 1. Put
 * together: the register a word FOLDS FROM is the one above the register it lands in, WHICH IS
 * ALSO WHERE THE NEXT WORD OF THE CELL LANDS. So a cell's five words are five steps from one
 * starting position and each word takes the step once, where naming both positions recomputed two
 * of mask_reg's conditional subtracts per word and scaled both — the 68000 has no scaled index
 * mode, so every `scratch[i]` was a multiply by four ahead of the access. Hence a pointer, and a
 * conditional wrap rather than a `%` for mask_reg's own reason. */
static uint32_t *next_reg(uint32_t *window, uint32_t *reg)
{
    return reg + 1 < window + WB_BLIT_SCRATCH_REGS ? reg + 1 : window;
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
static inline __attribute__((always_inline))
void blit_load_cell(const uint8_t *image, sprite_blit_regs *regs, unsigned cell,
                    int defer_last_merge, unsigned rotation, int row_in_image)
{
    uint32_t *window = regs->scratch;
    uint32_t *reg = window + mask_reg(cell);
    uint32_t source = regs->source;
    /* Which word's fold is held back, as a NUMBER — WB_BLIT_CELL_WORDS, one past the last, for the
     * columns and widths that have no such quirk. The quirk is a property of the whole cell, so
     * asking it once here leaves the loop one comparison rather than a test of both. */
    unsigned hold_back_word = defer_last_merge ? WB_BLIT_CELL_WORDS - 1u : WB_BLIT_CELL_WORDS;

    for (unsigned word = 0; word < WB_BLIT_CELL_WORDS; word++) {
        /* The cell's five words are the mask and then the four planes, in that order. */
        int is_mask = (word == 0);
        uint32_t loaded = rotate_right32((is_mask ? WB_BLIT_MASK_FILL : 0u)
                                             | blit_read_word(image, source, row_in_image),
                                         rotation);
        uint32_t *wrapped = next_reg(window, reg);

        source = addr_add(source, WB_STATE_WORD_LEN);
        if (cell == 0) {
            *reg = loaded;
        } else {
            int hold_back = (word == hold_back_word);

            *wrapped = swap_halves(*wrapped);
            *reg = hold_back ? loaded
                 : is_mask   ? and_wrapped_half(loaded, *wrapped)
                             : or_wrapped_half(loaded, *wrapped);
        }
        reg = wrapped;
    }
    /* THE CURSOR IS WALKED IN A LOCAL AND WRITTEN BACK ONCE, for include/scroll.h's
     * `copy_constant_longwords` reason and not merely for tidiness: while it lives behind the
     * caller's pointer GCC cannot prove a store through `image` does not alias it, so it must be
     * reloaded after every write and cannot be an induction variable. That comment carries the
     * measured before-and-after; here the licence is the same one — nothing between these five
     * reads looks at `regs->source`. */
    regs->source = source;
}

/* The row's LAST column is the last cell's wrapped half on its own, so all five of that cell's
 * registers are swapped and drawn from as they stand. */
static inline __attribute__((always_inline))
void blit_swap_cell(sprite_blit_regs *regs, unsigned cell)
{
    uint32_t *window = regs->scratch;
    uint32_t *reg = window + mask_reg(cell);

    for (unsigned word = 0; word < WB_BLIT_CELL_WORDS; word++) {
        *reg = swap_halves(*reg);
        reg = next_reg(window, reg);
    }
}

/* One 16-pixel column: `and.w mask,(a1) / or.w plane,(a1)+` per plane, the last of them without the
 * post-increment. The original spells the read-modify-write as two stores to the same word; one
 * store of the same value leaves the same byte and the same write set. */
static inline __attribute__((always_inline))
void blit_column(uint8_t *image, sprite_blit_regs *regs, unsigned cell, int is_last,
                 int row_in_image)
{
    uint32_t *window = regs->scratch;
    uint32_t *reg = window + mask_reg(cell);
    uint16_t mask = (uint16_t)*reg;
    uint32_t dest = regs->dest;

    for (unsigned plane = 0; plane < WB_PLANES; plane++) {
        uint16_t under = blit_read_word(image, dest, row_in_image);
        uint16_t plane_word;

        reg = next_reg(window, reg);
        plane_word = (uint16_t)*reg;
        blit_write_word(image, dest, (uint16_t)((under & mask) | plane_word), row_in_image);
        if (!(is_last && plane == WB_PLANES - 1))
            dest = addr_add(dest, WB_STATE_WORD_LEN);
    }
    regs->dest = dest;
}

/* One row of the sprite: `columns` columns drawn from `columns - 1` source cells. In a clipped body
 * a column whose bit is clear is stepped over instead of drawn, at the same cost, so this closes at
 * the same place either way.
 *
 * WRITTEN ONCE AND COMPILED TWICE, by the two wrappers under it. `row_in_image` is a constant in
 * each instantiation, so every test of it here and in the four helpers this inlines folds away and
 * each walk keeps ONE arm of the off-image guard and no test at all — which is the entire point of
 * asking that question per row. GCC does not clone a function on a constant argument by itself at
 * -O2 (that wants -fipa-cp-clone), so the specialisation is spelt rather than hoped for.
 *
 * `always_inline` is on the four helpers as well as on this, and it has to be BOTH: an earlier
 * attempt put it on the walk alone, and GCC answered by declining to inline blit_load_cell and
 * blit_column into the now-larger body — six arguments on the stack per cell and per column. */
static inline __attribute__((always_inline))
void blit_row_body(uint8_t *image, sprite_blit_regs *regs, const blit_width *width,
                   int clipped, unsigned rotation, int row_in_image)
{
    unsigned cells = width->columns - 1u;

    /* THE COLUMN LOOP IS UNROLLED, and that is what carries the width constant the rest of the way
     * down. `cell` is then a NUMBER in each copy, so mask_reg, plane_reg, next_reg and column_bit
     * all fold — where the rolled loop recomputed the window position per column and stepped the
     * pointer with a live wrap test per WORD (`cmp`/`bcs`/`move` against the window's end, ten
     * times a cell), each unrolled column now names its six registers by fixed displacement and
     * tests nothing. It is also what lets the register file above live in registers at all: SRA
     * only scalarises an array whose subscripts are constants. Measured at -O3, 2026-08-25.
     *
     * FIVE, SPELT AS A LITERAL, and the assertion sits here rather than in the header because
     * `#pragma` is one of the few places C does not macro-expand its argument — so the line below
     * is WB_BLIT_COLUMNS_MAX written a second time, and this is the pin CLAUDE.md §5 asks for when
     * a value has to be. A width wider than five columns changes the header and fails to compile
     * on the next line. THE PRAGMA IS A NO-OP AT -O2, where `width->columns` is a runtime load and
     * GCC declines to unroll it at all; src/scroll.c's copy run is unrolled the other way — the
     * copies SPELT OUT one after another — precisely because that file's runs must survive -O2 as
     * well. include/scroll.h's `copy_constant_run` states the other half of this note. */
    _Static_assert(WB_BLIT_COLUMNS_MAX == 5u,
                   "the `#pragma GCC unroll` below carries the widest column count as a literal, "
                   "and WB_BLIT_COLUMNS_MAX has moved away from it");
#pragma GCC unroll 5
    for (unsigned column = 0; column < width->columns; column++) {
        int is_last = (column == cells);
        unsigned cell = is_last ? cells - 1u : column;
        int defer = clipped && column == width->deferred_merge_column;

        if (is_last)
            blit_swap_cell(regs, cell);
        else
            blit_load_cell(image, regs, cell, defer, rotation, row_in_image);

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
        blit_column(image, regs, cell, is_last, row_in_image);
    }
}

/* The two instantiations. Each is a whole copy of the walk above with one arm of the guard in it.
 * `always_inline` for blit_row_body's own reason and for one more: a call that was not inlined would
 * take the address of blit_sprite_rows_body's local register file, and a file whose address escapes
 * is a file GCC must keep in memory. */
static inline __attribute__((always_inline))
void blit_row_walk_in_image(uint8_t *image, sprite_blit_regs *regs, const blit_width *width,
                            int clipped, unsigned rotation)
{
    blit_row_body(image, regs, width, clipped, rotation, WB_BLIT_ROW_IN_IMAGE);
}

static inline __attribute__((always_inline))
void blit_row_walk_checked(uint8_t *image, sprite_blit_regs *regs, const blit_width *width,
                           int clipped, unsigned rotation)
{
    blit_row_body(image, regs, width, clipped, rotation, WB_BLIT_ROW_CHECKED);
}

/* THE QUESTION BOTH HOISTS BELOW ASK, written once: a source span from a0 and a destination span
 * from a1, both wholly inside the image. Its two callers differ only in how far they stretch the
 * pair — over ONE row (blit_row) or over every row of the blit (blit_span_in_image) — so the
 * predicate is one function rather than the same conjunction spelt twice, and a change to what
 * "inside" means lands on both. */
static int spans_in_image(uint32_t source, uint32_t source_bytes,
                          uint32_t dest, uint32_t dest_bytes)
{
    return os_in_image(source, source_bytes) && os_in_image(dest, dest_bytes);
}

/* The row, plus the `lea` that steps the screen cursor to the next scanline — and THE OFF-IMAGE
 * GUARD, HOISTED OFF THE WORDS AND ONTO THE ROW.
 *
 * Inside the image a checked access IS the bare one: blit_read_word and blit_write_word differ from
 * `be16`/`wr16` only where blit_word_in_image says no, and the two tiers ask ONE question at two
 * widths — the word tier through os.h's constant-width `os_in_image_fixed`, this tier and the blit
 * tier through `spans_in_image`, and both of those reduce to the kit's `os_in_image`. So proving the
 * row's two spans lie inside the image
 * proves it for every word the walk goes on to touch — blit.h's WB_BLIT_ROW_SOURCE_BYTES and
 * WB_BLIT_ROW_DEST_BYTES are what makes that a PROOF and not a hope, and both are what a row really
 * touches rather than a word less. Where either span is not wholly inside, nothing is proved about
 * any of its words and each is asked as before: that is the runaway `dbf`'s 10 MB of screen, which
 * is exactly the case a hoist must not smuggle a write into.
 *
 * `blit_in_image` is the SAME PROOF taken one level further out, by blit_span_in_image below: when
 * the caller has already bounded every row of the blit, this row's own two questions have a known
 * answer and are not put. */
static inline __attribute__((always_inline))
void blit_row(uint8_t *image, sprite_blit_regs *regs, const blit_width *width, int clipped,
              unsigned rotation, int blit_in_image)
{
    if (blit_in_image
        || spans_in_image(regs->source, width->source_bytes, regs->dest, width->dest_bytes))
        blit_row_walk_in_image(image, regs, width, clipped, rotation);
    else
        blit_row_walk_checked(image, regs, width, clipped, rotation);
    regs->dest = addr_add(regs->dest, width->row_advance);
}

/* THE TWO LOOP SHAPES, READ OFF THE ENTRY COUNT BEFORE THE FIRST ROW: how many rows the shape
 * draws, and the word it leaves d7's low half at. NEITHER DEPENDS ON THE WALK, so the counter does
 * not have to live in a register across it — which is the whole point of asking here.
 *
 *   * `addq.w #1,d7 / tst.w d7 / beq / bmi`, the two-column bodies' guard: the bumped count is the
 *     number of rows, and the `dbf` at the bottom jumps back to the `tst`, so a positive count is
 *     stepped down to exactly zero. A count that is not positive draws nothing and is left where it
 *     stands — the `beq` and the `bmi` exit without touching it again.
 *   * `dbf d7,<top>` alone: the row is drawn before the count is looked at, so an entry value of N
 *     draws N + 1 rows — 65,536 for $ffff, the negative-height runaway the pass reaches — and the
 *     exit condition IS the counter back at $ffff, whatever it entered as.
 *
 * The 68000 has eight data registers and one row needs all of them: the six-word source window, the
 * rotation count and one temporary to merge a screen word through. A counter stepped per row is a
 * ninth, and the two it displaced were spilled to the stack and reloaded every row (measured at -O3,
 * 2026-08-26: 1074 cycles a row at three columns, against the original's 758). */
typedef struct {
    uint32_t rows;        /* rows drawn — up to 65,536, so this is a longword and not d7's word */
    uint16_t exit_count;  /* the low word of d7 the caller gets back */
} blit_row_count;

static blit_row_count blit_count_rows(uint32_t rows, int counts_rows_up_front)
{
    int16_t bumped = (int16_t)(uint16_t)(rows + 1u);
    blit_row_count counted;

    if (!counts_rows_up_front) {
        counted.rows = (uint32_t)(uint16_t)rows + 1u;
        counted.exit_count = (uint16_t)-1;
        return counted;
    }
    counted.rows = bumped > 0 ? (uint32_t)bumped : 0u;
    counted.exit_count = bumped > 0 ? 0u : (uint16_t)bumped;
    return counted;
}

/* ...AND THE SAME GUARD HOISTED AGAIN, OFF THE ROW AND ONTO THE WHOLE BLIT. Both cursors advance
 * MONOTONICALLY across the rows and by a fixed step — the source by one row's cells, the screen by
 * WB_BLIT_ROW_DEST_STEP (blit.h) — so the union of every row's span is ONE span on each side, and
 * os_in_image over those two decides for every row the blit will draw at once. Where it holds,
 * blit_row's own question could only ever be answered yes and is not asked; where it does not,
 * NOTHING is proved about any row and blit_row asks per row exactly as before. That fallback is not
 * a nicety: it is what keeps the runaway `dbf`'s 65,536 rows dropping their off-image writes one at
 * a time, as the oracle's bus does.
 *
 * `rows` is the number the caller's loop will DRAW. Neither product can overflow a longword: `rows`
 * is at most 65,536, one row's source is at most WB_BLIT_ROW_SOURCE_BYTES(WB_BLIT_COLUMNS_MAX) and
 * the screen span at most that many whole scanlines. */
static int blit_span_in_image(const sprite_blit_regs *regs, const blit_width *width, uint32_t rows)
{
    /* BOTH SHAPES REACH THIS WITH A COUNT OF ZERO — the counted one every time it refuses its
     * count, since the single call below asks for both shapes rather than short-circuiting on one —
     * and this guard is what makes that safe: the `rows - 1u` on the next line would otherwise
     * underflow into a 4 GB span that answers yes to everything. It FAILS CLOSED on purpose, and a
     * shape added later gets the same answer: a blit that touches nothing has nothing proved about
     * it, and saying so costs only the per-row question a walk of no rows never asks. */
    if (rows == 0)
        return 0;
    return spans_in_image(regs->source, rows * width->source_bytes,
                          regs->dest, (rows - 1u) * WB_BLIT_ROW_DEST_STEP + width->dest_bytes);
}

/* The whole blit: the rows this width's loop shape draws, and the counter it leaves behind. Both
 * come off the entry state before the first row, which is also what bounds the walk — one decision
 * for the blit rather than one per row.
 *
 * THE REGISTER FILE IS A LOCAL FOR THE LENGTH OF THE BLIT and the caller's is written back once,
 * which is what the 68000 does with d0..d7/a0/a1 and what this port could not do while every word
 * reached the file through the caller's pointer: a store through `image` may alias `*regs` for all
 * GCC knows, so each of the window's six words and both cursors had to be re-read after every plane
 * the walk had written. Nothing outside this function can see `file` — which is why the two walks
 * above are `always_inline` — so with the column loop unrolled its subscripts are constants and the
 * whole file lives in registers for the whole walk. blit_load_cell already made this argument for
 * the source cursor within ONE cell; this is the same one, for the whole blit.
 *
 * AND IT IS COMPILED ONCE PER CLIP CASE, by the two functions under it, for the same reason the row
 * walk is compiled once per guard arm: `clipped` decides three things per column — the `btst`, the
 * step over an undrawn column and the deferred merge — and while it was a runtime argument GCC held
 * ONE body for both cases and allocated registers for the harder of the two. The window needs all
 * eight data registers (see blit_count_rows), so there was nothing left to pay a clipped body's
 * extra live values out of: measured at -O3 on 2026-08-26, the three-column unclipped row spilled a
 * window word to the stack, parked four more in address registers and cost 1004 cycles, against 924
 * with the two cases compiled apart.
 *
 * THE PRICE IS TEXT, and it is the one thing in this file that is not free: the two cases no longer
 * share their tails, so the walk is assembled eight times over — four table_mid entries with the
 * unclipped body inlined into them, four per-width clones of the clipped one — where before it was
 * assembled four times. That is several clusters of the boot floppy's remaining headroom, and
 * atari/build.sh's own -O3 accounting is the ledger it belongs in (tools/st_build.py refuses an
 * overflow rather than truncating). What buys it is where the walking frame spends its sprite pass:
 * blit_sprite_w3 and blit_clip_right_w3 are ~95 % of it. Both sides of the trade are measured in
 * ../STATUS.md, "## Performance". Undoing it is three lines — the `always_inline` above, the two
 * wrappers below and their call sites. */
static inline __attribute__((always_inline))
void blit_sprite_rows_body(uint8_t *image, sprite_blit_regs *regs, const blit_width *width,
                           int clipped)
{
    sprite_blit_regs file = *regs;
    unsigned rotation = blit_rotation(&file);
    blit_row_count counted = blit_count_rows(file.rows, width->counts_rows_up_front);
    /* A shape that refuses its count draws nothing, and blit_span_in_image answers a span of no
     * rows with a no of its own — so the bound is asked once here for both shapes. */
    int blit_in_image = blit_span_in_image(&file, width, counted.rows);

    for (uint32_t left = counted.rows; left != 0; left--)
        blit_row(image, &file, width, clipped, rotation, blit_in_image);

    /* ONE write-back for both shapes, counter included: the exit value is blit_count_rows'
     * business, so a shape added here cannot forget to leave the caller's registers where the
     * original does.
     *
     * THIS IS WHERE THE d7 INVARIANT IS LOAD-BEARING. `file.rows` is d7, and nothing between here
     * and the copy at the top of this function writes it — the walk takes its trip count from
     * `counted`, and `counted.exit_count` was decided before the first row — so the HIGH half being
     * written back is still the caller's own, which is what the original leaves there (every body
     * touches d7 as a word). A walk that stepped `file.rows` per row would both lose that half and
     * make this `set_low_word` overwrite a counter it no longer owns. */
    file.rows = set_low_word(file.rows, counted.exit_count);
    *regs = file;
}

/* The two clip cases of that body. Each is `blit_sprite_rows` for the entry points below it — the
 * four table_mid ones reach the first, the eight preludes the second — and -O3 specialises each per
 * width, by whichever route is cheaper for its call count: the plain one has four callers and is
 * INLINED into all four, leaving no out-of-line body at all, while the clipped one's eight callers
 * get four `-fipa-cp-clone` clones, one per width table entry. atari/build.sh checks for BOTH
 * outcomes after the link, because either of them de-specialising is the same lost frame. */
static void blit_sprite_rows_plain(uint8_t *image, sprite_blit_regs *regs, const blit_width *width)
{
    blit_sprite_rows_body(image, regs, width, WB_BLIT_UNCLIPPED);
}

static void blit_sprite_rows_clipped(uint8_t *image, sprite_blit_regs *regs,
                                     const blit_width *width)
{
    blit_sprite_rows_body(image, regs, width, WB_BLIT_CLIPPED);
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
            blit_sprite_rows_clipped(image, regs, width);
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
            blit_sprite_rows_clipped(image, regs, width);
            return;
        }
    }
}

/* --- the twelve entry points --------------------------------------------------------------------- */

void blit_sprite_w2(uint8_t *image, sprite_blit_regs *regs)
{
    blit_sprite_rows_plain(image, regs, &BLIT_W2);
}

void blit_sprite_w3(uint8_t *image, sprite_blit_regs *regs)
{
    blit_sprite_rows_plain(image, regs, &BLIT_W3);
}

void blit_sprite_w4(uint8_t *image, sprite_blit_regs *regs)
{
    blit_sprite_rows_plain(image, regs, &BLIT_W4);
}

void blit_sprite_w5(uint8_t *image, sprite_blit_regs *regs)
{
    blit_sprite_rows_plain(image, regs, &BLIT_W5);
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


/* --- the sprite pass at $8f02 ------------------------------------------------------------------
 *
 * The twelve above draw; this decides WHAT and WHERE. Once per frame it walks the nineteen screen
 * records project_actor_list left at WB_ACTOR_SCREEN_RECORDS and, for each one whose sprite word is
 * not WB_ACTOR_SPRITE_HIDDEN, looks that sprite's descriptor up in WB_RESOURCE_TABLE, clips it to
 * the band, builds the blitters' register file and calls one of them. It writes NOTHING itself:
 * every byte the pass is responsible for goes through a blitter.
 *
 * FOUR THINGS ARE REPRODUCED RATHER THAN TIDIED, all of them read off the listing:
 *
 *   * THE DESCRIPTOR CURSOR IS A WORD INDEX. `mulu.w #$14,d0` builds a 32-bit product and
 *     `adda.w d0,a4` then takes only its SIGN-EXTENDED LOW WORD, so a sprite index past 3276 wraps
 *     the cursor rather than walking off the table, and one whose product's low word has bit 15 set
 *     moves it BACKWARDS. The reachable band is therefore WB_RESOURCE_TABLE +- 32 KB and nothing
 *     wider — which is why nothing here needs an in-image guard. Same class as the word-indexed
 *     `lea` batch 13 pinned.
 *   * A NEGATIVE ROW COUNT SURVIVES THE BOTTOM CLAMP. The height is a byte the original `ext.w`s,
 *     so a descriptor may ask for -1 rows; the clamp is `cmp.w d7,d2 / bge` with d2 the rows left
 *     in the band, which is never negative, so it always keeps a negative d7 rather than clamping
 *     it. That count reaches a blitter, where the two-column bodies refuse it and the three wider
 *     ones run away. THE TOP CLIP CANNOT PRODUCE ONE: its own `bmi` skips the record instead.
 *   * `move.w d1,d5` IS DEAD. Nothing in the pass or in any of the twelve reads d5 before writing
 *     it. It is reproduced because it is a register the caller gets back.
 *   * THE SCREEN OFFSET IS BUILT IN SIXTEEN BITS and only then sign-extended into a1, so a large x
 *     or y wraps inside the word instead of reaching where the arithmetic points.
 */

/* The twelve, in the order the three jump tables hold them: width code 0..3 is
 * WB_BLIT_COLUMNS_MIN..WB_BLIT_COLUMNS_MAX columns. Calling them by that index is a READING of the
 * image and not a shortcut — test/test_blit.py's `test_a_jump_table_names_the_four_widths_in_order`
 * requires each table to hold exactly these four addresses in this order, and
 * `test_the_three_tables_are_the_only_things_that_name_a_blitter` that nothing else in the program
 * names any of them. The pass still reads the slot it would have `jsr`ed through, because that
 * pointer is one of the registers it leaves behind. */
typedef void (*sprite_blitter)(uint8_t *image, sprite_blit_regs *regs);

/* One clip case: the table in the image, and this port's four entry points behind it. */
typedef struct {
    uint32_t table;
    const sprite_blitter *blitters;
} sprite_clip_case;

static const sprite_blitter SPRITE_BLITTERS_MID[] = {
    blit_sprite_w2, blit_sprite_w3, blit_sprite_w4, blit_sprite_w5,
};
static const sprite_blitter SPRITE_BLITTERS_LEFT[] = {
    blit_clip_left_w2, blit_clip_left_w3, blit_clip_left_w4, blit_clip_left_w5,
};
static const sprite_blitter SPRITE_BLITTERS_RIGHT[] = {
    blit_clip_right_w2, blit_clip_right_w3, blit_clip_right_w4, blit_clip_right_w5,
};

static const sprite_clip_case SPRITE_CLIP_MID   = {WB_BLIT_TABLE_MID, SPRITE_BLITTERS_MID};
static const sprite_clip_case SPRITE_CLIP_LEFT  = {WB_BLIT_TABLE_LEFT, SPRITE_BLITTERS_LEFT};
static const sprite_clip_case SPRITE_CLIP_RIGHT = {WB_BLIT_TABLE_RIGHT, SPRITE_BLITTERS_RIGHT};

/* A `.w` write into one of d0..d5, which is every write the pass makes to that window. */
static void set_scratch_word(sprite_blit_regs *blit, unsigned reg, uint16_t value)
{
    blit->scratch[reg] = set_low_word(blit->scratch[reg], value);
}

/* $8f36..$8f52 — the sprite starts ABOVE the band, so the rows that fall off the top come out of
 * both the count and the SOURCE. `muls.w d1,d0` multiplies one row's bytes by the NEGATIVE y, so
 * the product is negative and the `suba.l d0,a0` under it ADDS that magnitude to the source cursor,
 * stepping it past the clipped rows. Returns 0 when nothing of the sprite is left to draw, which is
 * the `bmi` that skips the record. */
static int sprite_clip_top(const uint8_t *descriptor, sprite_blit_regs *blit, int16_t *y)
{
    int16_t rows = (int16_t)(uint16_t)((uint16_t)blit->rows + (uint16_t)*y);

    blit->rows = set_low_word(blit->rows, (uint16_t)rows);
    if (rows < 0)
        return 0;

    /* `move.b 4(a4),d0 / ext.w / addq.w #1` — the width code plus one IS the number of source cells
     * in a row, since code 0 is WB_BLIT_COLUMNS_MIN columns and N columns come from N-1 cells. */
    uint16_t cells = (uint16_t)(sign_ext8(descriptor[WB_SPRITE_DESC_WIDTH_CODE]) + 1u);
    uint32_t row_bytes = (uint32_t)cells * (WB_BLIT_CELL_WORDS * WB_STATE_WORD_LEN);  /* mulu.w */
    int32_t clipped = (int32_t)(int16_t)(uint16_t)row_bytes * (int32_t)*y;            /* muls.w */

    blit->scratch[WB_SPRITE_WORK_REG] = (uint32_t)clipped;
    blit->source = addr_add(blit->source, 0u - (uint32_t)clipped);
    *y = 0;
    set_scratch_word(blit, WB_SPRITE_Y_REG, 0);
    return 1;
}

/* $8f5c..$8f66 — the sprite starts INSIDE the band, so the count is cut down to the rows left of
 * it. The compare is signed and the rows left are never negative, which is the second bullet of the
 * section comment: a negative count is kept, not clamped. The original builds the rows left IN d2
 * (`move.w #$9f,d2 / sub.w d1,d2`); that write is not reproduced, per the register-file policy in
 * sprite_draw_record's comment — the width code overwrites d2 before any exit from the pass. */
static void sprite_clamp_rows_to_band(sprite_blit_regs *blit, int16_t y)
{
    int16_t rows_left = (int16_t)(WB_SPRITE_LAST_ROW - y);

    if (rows_left < (int16_t)(uint16_t)blit->rows)
        blit->rows = set_low_word(blit->rows, (uint16_t)rows_left);
}

/* $8f68..$8f98 — the screen cursor for (x, y): WB_SCREEN_BACK plus the window's origin plus a
 * SIXTEEN-BIT offset, sign-extended by the `adda.w`. `y` is 0..WB_SPRITE_LAST_ROW on both paths in,
 * so the two `asl.w`s never shift a negative; they leave the y register holding y << 7. */
static void sprite_screen_cursor(const uint8_t *image, sprite_blit_regs *blit, uint16_t x, int16_t y)
{
    uint16_t column = (uint16_t)((int16_t)(uint16_t)(x & WB_SPRITE_COLUMN_MASK)
                                 >> WB_SPRITE_X_BYTE_SHIFT);
    uint16_t row = (uint16_t)((uint16_t)y << WB_SPRITE_ROW_SHIFT_LOW);
    uint16_t offset;

    blit->dest = addr_add(be32(image + WB_SCREEN_BACK), WB_BG_BLIT_SCREEN_ORIGIN);
    set_scratch_word(blit, WB_SPRITE_Y_REG, row);
    offset = (uint16_t)(column + row);

    row = (uint16_t)(row << WB_SPRITE_ROW_SHIFT_HIGH);
    set_scratch_word(blit, WB_SPRITE_Y_REG, row);
    offset = (uint16_t)(offset + row);

    set_scratch_word(blit, WB_SPRITE_WORK_REG, offset);
    blit->dest = addr_add(blit->dest, sign_ext16(offset));
}

/* $8f9a..$8fbc — which table, which slot, and the call. Both tests are SIGNED and they run in this
 * order, so a negative x reaches the left table and stays there: it is below the right threshold
 * too. */
static void sprite_dispatch(uint8_t *image, sprite_pass_regs *regs, int16_t x, int16_t width_code)
{
    sprite_blit_regs *blit = &regs->blit;
    const sprite_clip_case *clip = &SPRITE_CLIP_MID;
    uint16_t slot = (uint16_t)((uint16_t)width_code << WB_BLIT_TABLE_SLOT_SHIFT);

    if (x < 0)
        clip = &SPRITE_CLIP_LEFT;
    if (x >= (int16_t)WB_SPRITE_RIGHT_CLIP_X)
        clip = &SPRITE_CLIP_RIGHT;

    /* `lsl.w #2,d2`, which is where the width code stops being the width code. */
    set_scratch_word(blit, WB_SPRITE_WIDTH_REG, slot);

    /* A width code outside 0..WB_BLIT_WIDTH_CODE_MAX indexes past the four-longword table and the
     * original `jsr`s through whatever longword the arithmetic lands on. Nothing in this port can
     * stand in for that, so it is the one input test/test_blit.py refuses; the guard is what keeps
     * the C from indexing its own table out of bounds, and it declines the `movea.l (a2),a2` as
     * well because that read is one address past the table for the same reason.
     *
     * IT IS ALSO WHY THE `ext.w d2` ABOVE CANNOT BE PINNED. A width code with bit 7 set is the only
     * input the sign extension changes, and every such code lands here — so no case that RUNS can
     * tell the signed reading from the unsigned one, and the mutation sweep records it as such. The
     * signed reading is the instruction's, taken from the listing and from the entry pin's bytes. */
    if ((unsigned)width_code > WB_BLIT_WIDTH_CODE_MAX)
        return;

    regs->blitter = be32(image + addr_add(clip->table, sign_ext16(slot)));
    clip->blitters[width_code](image, blit);
}

/* One screen record, $8f0e..$8fbc. Every skip in the original is an early return here.
 *
 * Register map: WB_SPRITE_WORK_REG = d0 (the sprite index, then two products, then the screen
 * offset), WB_SPRITE_Y_REG = d1, WB_SPRITE_WIDTH_REG = d2, WB_BLIT_X_REG = d4,
 * WB_SPRITE_ECHO_Y_REG = d5, shift = d6, rows = d7, source = a0, dest = a1, descriptor = a4,
 * record = a6.
 *
 * WHAT "THE REGISTER FILE" MEANS HERE. This models the file at the points a caller can OBSERVE it —
 * every exit from the pass — and not the asm's intermediate temporal states, so a write a later
 * instruction unconditionally overwrites before any exit is not reproduced (the rows-left value the
 * bottom clamp builds in d2 is the one such write; the width code lands on top of it). An
 * intermediate is kept only where it IS observable: `move.w d1,d5` below is dead to this pass and
 * to all twelve blitters, but a wholly-off-screen sprite's prelude returns without touching a data
 * register, so that copy is the last thing d5 saw and a case reads it back.
 */
static void sprite_draw_record(uint8_t *image, sprite_pass_regs *regs)
{
    sprite_blit_regs *blit = &regs->blit;
    const uint8_t *record = image + regs->record;
    const uint8_t *descriptor;
    uint16_t sprite;
    uint16_t x;
    int16_t width_code;
    int16_t y;

    /* `clr.w d0 / clr.w d1` sit AHEAD of the sprite word's own test, so even a skipped record
     * leaves the pair at zero. */
    set_scratch_word(blit, WB_SPRITE_WORK_REG, 0);
    set_scratch_word(blit, WB_SPRITE_Y_REG, 0);

    sprite = be16(record + WB_ACTOR_SCREEN_SPRITE);
    set_scratch_word(blit, WB_SPRITE_WORK_REG, sprite);
    if (sprite == WB_ACTOR_SPRITE_HIDDEN)
        return;

    /* The word index and its wrap — the first bullet of the section comment. */
    blit->scratch[WB_SPRITE_WORK_REG] = (uint32_t)sprite * WB_RESOURCE_RECORD_BYTES;
    regs->descriptor = addr_add(regs->descriptor,
                                sign_ext16(blit->scratch[WB_SPRITE_WORK_REG]));
    descriptor = image + regs->descriptor;

    blit->rows = set_low_word(blit->rows,
                              (uint16_t)sign_ext8(descriptor[WB_SPRITE_DESC_HEIGHT]));
    blit->source = be32(descriptor + WB_SPRITE_DESC_SOURCE);

    y = (int16_t)(uint16_t)(be16(record + WB_ACTOR_SCREEN_Y)
                            + be16(descriptor + WB_SPRITE_DESC_Y_OFFSET));
    set_scratch_word(blit, WB_SPRITE_Y_REG, (uint16_t)y);
    if (y < 0) {
        if (!sprite_clip_top(descriptor, blit, &y))
            return;
    } else {
        if (y > (int16_t)WB_SPRITE_LAST_ROW)
            return;
        sprite_clamp_rows_to_band(blit, y);
    }

    set_scratch_word(blit, WB_SPRITE_ECHO_Y_REG, (uint16_t)y);
    x = (uint16_t)(be16(record + WB_ACTOR_SCREEN_X)
                   + be16(descriptor + WB_SPRITE_DESC_X_OFFSET));
    set_scratch_word(blit, WB_SPRITE_WORK_REG, x);
    set_scratch_word(blit, WB_BLIT_X_REG, x);

    width_code = (int16_t)sign_ext8(descriptor[WB_SPRITE_DESC_WIDTH_CODE]);
    set_scratch_word(blit, WB_SPRITE_WIDTH_REG, (uint16_t)width_code);
    blit->shift = set_low_word(blit->shift, x & WB_SPRITE_SHIFT_MASK);

    sprite_screen_cursor(image, blit, x, y);
    sprite_dispatch(image, regs, (int16_t)x, width_code);
}

void sprite_draw_pass(uint8_t *image, sprite_pass_regs *regs)
{
    regs->record = WB_ACTOR_SCREEN_RECORDS;
    do {
        /* `lea $248d8.l,a4` is INSIDE the loop: every record indexes the table from its own base,
         * so one record's wrapped cursor cannot carry into the next. */
        regs->descriptor = WB_RESOURCE_TABLE;
        sprite_draw_record(image, regs);
        regs->record = addr_add(regs->record, WB_ACTOR_SCREEN_RECORD_BYTES);
    } while ((int32_t)regs->record < (int32_t)WB_ACTOR_SCREEN_RECORDS_END);
}
