/* main.c — the raycast spike's driver: build the world, cast the rays, time the four stages.
 *
 * Nothing here is a hot loop. Every per-pixel cost lives in render.S; this file decides WHAT the
 * asm is asked to draw and MEASURES how long it took, which is the whole point of the milestone.
 *
 * The frame is rendered straight to Physbase — the screen the shifter is really displaying — so
 * what the timer measures is what a Hatari screenshot shows, with no off-screen buffer to make the
 * numbers prettier than the picture.
 */
#include "spike.h"
#include "tables.h"

/* ---------------------------------------------------------------- the asm side ---------------- */
typedef struct {
    unsigned short tex_offset;          /* bytes from the shade's texture base    RAY_TEX_OFFSET */
    short top;                          /* first logical row of the wall          RAY_TOP        */
    short rows;                         /* wall rows, already clipped to the view RAY_ROWS       */
    short pad;                          /* keeps the two longwords aligned                       */
    unsigned long tex_pos;              /* 16.16, integer part is a texel index   RAY_TEX_POS    */
    unsigned long tex_step;             /* 16.16 per logical row                  RAY_TEX_STEP   */
} SpikeRay;

typedef struct {
    unsigned short *chunky;             /* band_top's chunky row, pair 0          DRAW_CHUNKY    */
    const SpikeRay *rays;               /*                                        DRAW_RAYS      */
    const unsigned short *tex_even;     /*                                        DRAW_TEX_EVEN  */
    const unsigned short *tex_odd;      /*                                        DRAW_TEX_ODD   */
    short pairs;                        /* columns / 2                            DRAW_PAIRS     */
    short stride;                       /* chunky bytes per logical row           DRAW_STRIDE    */
    short band_top;                     /*                                        DRAW_BAND_TOP  */
    short band_bottom;                  /*                                     DRAW_BAND_BOTTOM  */
    unsigned short ceil_even;           /* already pair-scaled                  DRAW_CEIL_EVEN   */
    unsigned short ceil_odd;            /*                                      DRAW_CEIL_ODD    */
    unsigned short floor_even;          /*                                      DRAW_FLOOR_EVEN  */
    unsigned short floor_odd;           /*                                      DRAW_FLOOR_ODD   */
} SpikeDrawJob;

_Static_assert(__builtin_offsetof(SpikeRay, tex_offset)     == RAY_TEX_OFFSET,   "RAY_TEX_OFFSET");
_Static_assert(__builtin_offsetof(SpikeRay, top)            == RAY_TOP,          "RAY_TOP");
_Static_assert(__builtin_offsetof(SpikeRay, rows)           == RAY_ROWS,         "RAY_ROWS");
_Static_assert(__builtin_offsetof(SpikeRay, tex_pos)        == RAY_TEX_POS,      "RAY_TEX_POS");
_Static_assert(__builtin_offsetof(SpikeRay, tex_step)       == RAY_TEX_STEP,     "RAY_TEX_STEP");
_Static_assert(sizeof(SpikeRay)                             == RAY_SIZEOF,       "RAY_SIZEOF");
_Static_assert(__builtin_offsetof(SpikeDrawJob, chunky)     == DRAW_CHUNKY,      "DRAW_CHUNKY");
_Static_assert(__builtin_offsetof(SpikeDrawJob, rays)       == DRAW_RAYS,        "DRAW_RAYS");
_Static_assert(__builtin_offsetof(SpikeDrawJob, tex_even)   == DRAW_TEX_EVEN,    "DRAW_TEX_EVEN");
_Static_assert(__builtin_offsetof(SpikeDrawJob, tex_odd)    == DRAW_TEX_ODD,     "DRAW_TEX_ODD");
_Static_assert(__builtin_offsetof(SpikeDrawJob, pairs)      == DRAW_PAIRS,       "DRAW_PAIRS");
_Static_assert(__builtin_offsetof(SpikeDrawJob, stride)     == DRAW_STRIDE,      "DRAW_STRIDE");
_Static_assert(__builtin_offsetof(SpikeDrawJob, band_top)   == DRAW_BAND_TOP,    "DRAW_BAND_TOP");
_Static_assert(__builtin_offsetof(SpikeDrawJob, band_bottom) == DRAW_BAND_BOTTOM, "DRAW_BAND_BOTTOM");
_Static_assert(__builtin_offsetof(SpikeDrawJob, ceil_even)  == DRAW_CEIL_EVEN,   "DRAW_CEIL_EVEN");
_Static_assert(__builtin_offsetof(SpikeDrawJob, ceil_odd)   == DRAW_CEIL_ODD,    "DRAW_CEIL_ODD");
_Static_assert(__builtin_offsetof(SpikeDrawJob, floor_even) == DRAW_FLOOR_EVEN,  "DRAW_FLOOR_EVEN");
_Static_assert(__builtin_offsetof(SpikeDrawJob, floor_odd)  == DRAW_FLOOR_ODD,   "DRAW_FLOOR_ODD");
_Static_assert(sizeof(SpikeDrawJob)                         == DRAW_SIZEOF,      "DRAW_SIZEOF");
_Static_assert(sizeof(unsigned long) == 4, "the ledger is published a longword at a time");

void spike_draw_columns(const SpikeDrawJob *job);
void spike_c2p_high(const unsigned short *chunky, unsigned char *screen, int rows);
void spike_c2p_low(const unsigned short *chunky, unsigned char *screen, int rows);
void spike_fill(void *dst, long bytes, unsigned long plane01, unsigned long plane23);
unsigned long spike_ticks(void);
unsigned long spike_timer_c_read(void);
unsigned short spike_divu(unsigned long numerator, unsigned short denominator);

/* ---------------------------------------------------------------- the TOS side ---------------- */
long Fcreate(const char *name, short attr);
long Fclose(short handle);
long Fwrite(short handle, long count, const void *buf);
void Cconws(const char *text);
long Super(void *stack);
long spike_leave_supervisor(void *ssp);
long Physbase(void);

/* ---------------------------------------------------------------- the world ------------------- */
/* Named by render.S, so these two keep their unprefixed C names and external linkage. */
unsigned long spike_c2p_table_high[C2P_POSITIONS_HIGH * C2P_PAIR_COUNT * 2];
unsigned long spike_c2p_table_low[C2P_POSITIONS_LOW * C2P_PAIR_COUNT * 2];

static unsigned short g_tex_even[TEX_WORDS];    /* texel * PAIR_EVEN_SCALE, column-major */
static unsigned short g_tex_odd[TEX_WORDS];     /* texel * PAIR_ODD_SCALE                */
static unsigned char g_map[MAP_CELLS];
static unsigned short g_chunky[CHUNKY_WORDS];

static SpikeRay g_rays[VIEW_W_HIGH];            /* one raycast frame, consumed by the drawer */
static short g_band_top;
static short g_band_bottom;

static long g_pos_x, g_pos_y;                   /* 16.16 world position, in map cells */
static long g_dir_x, g_dir_y, g_plane_x, g_plane_y;
static long g_ray_start_x, g_ray_start_y;       /* column 0's ray direction, 16.16 shifted up 8 */
static long g_ray_step_x, g_ray_step_y;         /* ...and the constant step from column to column */
static short g_angle;                           /* BRAD_FULL units per turn */
static unsigned char *g_screen;

/* ---------------------------------------------------------------- the ledger ------------------ */
typedef struct {
    unsigned long columns;
    unsigned long rotating;
    unsigned long banded;
    unsigned long ticks_raycast;
    unsigned long ticks_columns;
    unsigned long ticks_fill;
    unsigned long ticks_c2p;
    unsigned long ticks_total;
    unsigned long band_top_sum;
    unsigned long band_bottom_sum;
} SpikePassLedger;

typedef struct {
    unsigned long magic;                /* written LAST: its arrival means the rest is complete */
    unsigned long version;
    unsigned long tick_ns;
    unsigned long cpu_hz;
    unsigned long frames;
    unsigned long timer_c_max;          /* the run's own check on TIMER_C_RELOAD */
    unsigned long passes;
    unsigned long screen;
    SpikePassLedger pass[SPIKE_PASSES];
} SpikeLedger;

static SpikeLedger g_ledger;

static const struct { short width; short rotating; short banded; } g_pass_plan[SPIKE_PASSES] = {
    { VIEW_W_HIGH, 0, 1 }, { VIEW_W_HIGH, 1, 1 }, { VIEW_W_HIGH, 0, 0 }, { VIEW_W_HIGH, 1, 0 },
    { VIEW_W_LOW,  0, 1 }, { VIEW_W_LOW,  1, 1 }, { VIEW_W_LOW,  0, 0 }, { VIEW_W_LOW,  1, 0 },
};

/* ---------------------------------------------------------------- palette --------------------- */
/* THE STE'S NIBBLE IS NOT THE VALUE. Its palette registers kept the ST's three bits where they
 * were (register bits 2-0) and bolted the new fourth bit on as bit 3, where it is the LEAST
 * significant bit of the intensity. So an intensity is rotated, not just widened, and hand-encoding
 * a colour word gets it wrong in a way that looks almost right. */
static unsigned short ste_nibble(int intensity)
{
    return (unsigned short)(((intensity >> 1) & 7) | ((intensity & 1) << 3));
}

static unsigned short ste_colour(int red, int green, int blue)
{
    return (unsigned short)((ste_nibble(red) << 8) | (ste_nibble(green) << 4) | ste_nibble(blue));
}

/* Pen 0 black (it is also the border the shifter shows outside the 320x200), pen 1 the ceiling,
 * pen 2 the floor and pen 3 white, then TEX_COUNT families of PEN_FAMILY_LEVELS intensities. A wall's dark side is the
 * same texture one level down inside its own family, which is how 16 pens carry lit and unlit
 * faces of four different materials. */
static const unsigned char g_palette_rgb[PALETTE_PENS][3] = {
    {  0,  0,  0 }, {  2,  2,  3 }, {  4,  3,  2 }, { 15, 15, 15 },
    {  5,  1,  1 }, {  9,  3,  2 }, { 13,  5,  3 },     /* family 0: brick   */
    {  4,  4,  5 }, {  8,  8,  9 }, { 12, 12, 13 },     /* family 1: stone   */
    {  1,  4,  1 }, {  3,  8,  3 }, {  5, 12,  5 },     /* family 2: moss    */
    {  1,  2,  5 }, {  3,  5,  9 }, {  5,  8, 13 },     /* family 3: panel   */
};

static void set_palette(void)
{
    volatile unsigned short *pen = (volatile unsigned short *)PALETTE_ADDR;
    int i;
    for (i = 0; i < PALETTE_PENS; i++) {
        pen[i] = ste_colour(g_palette_rgb[i][0], g_palette_rgb[i][1], g_palette_rgb[i][2]);
    }
}

/* ---------------------------------------------------------------- c2p tables ------------------ */
/* One entry per (position, pixel pair): the four plane words a pair contributes to its 16-screen-
 * pixel group, packed as planes 0/1 then 2/3 so the loop stores two longwords and nothing else.
 * `pixel_span` is how many screen pixels one logical pixel covers — 2 at high detail, 4 at low —
 * and it is the ONLY difference between the two tables. */
static void build_c2p_table(unsigned long *table, int positions, int pixel_span)
{
    int position, even, odd, plane;
    for (position = 0; position < positions; position++) {
        for (even = 0; even < 16; even++) {
            for (odd = 0; odd < 16; odd++) {
                unsigned long word[SCREEN_PLANES];
                int pair = even * 16 + odd;
                int even_shift = 16 - (position * 2 + 1) * pixel_span;
                int odd_shift = even_shift - pixel_span;
                unsigned long span_mask = (1UL << pixel_span) - 1;
                unsigned long *entry = table + (position * C2P_PAIR_COUNT + pair) * 2;
                for (plane = 0; plane < SCREEN_PLANES; plane++) {
                    word[plane] = (((even >> plane) & 1) ? (span_mask << even_shift) : 0)
                                | (((odd >> plane) & 1) ? (span_mask << odd_shift) : 0);
                }
                entry[0] = (word[0] << 16) | word[1];
                entry[1] = (word[2] << 16) | word[3];
            }
        }
    }
}

/* ---------------------------------------------------------------- textures -------------------- */
/* Four procedural 64x64 materials, each texel one of PEN_FAMILY_LEVELS intensities. Deterministic:
 * the same frame comes out of every run, which is what makes a timing comparison a comparison. */
static int texel_hash(int u, int v)
{
    return ((u * 73 + v * 151) ^ (u * v * 29)) & 0xff;
}

static int texel_level(int material, int u, int v)
{
    switch (material) {
    case 0:                                             /* brick: courses with staggered joints */
        if ((v & 15) == 0) return 0;
        if (((u + ((v >> 4) & 1) * 16) & 31) == 0) return 0;
        return (texel_hash(u, v) & 7) == 0 ? 1 : 2;
    case 1:                                             /* rough stone */
        return texel_hash(u, v) % PEN_FAMILY_LEVELS;
    case 2:                                             /* mossy planks: vertical grain */
        if ((u & 7) == 0) return 0;
        return ((v + (u >> 3)) & 3) == 0 ? 1 : 2;
    default:                                            /* riveted panel */
        if ((u & 15) == 0 || (v & 15) == 0) return 0;
        return (((u & 15) == 8) && ((v & 15) == 8)) ? 2 : 1;
    }
}

static void build_textures(void)
{
    int material, shade, u, v;
    for (material = 0; material < TEX_COUNT; material++) {
        for (shade = 0; shade < TEX_SHADES; shade++) {
            for (u = 0; u < TEX_SIZE; u++) {
                unsigned short *even = g_tex_even + ((material * TEX_SHADES + shade) * TEX_SIZE + u)
                                                    * TEX_COL_WORDS;
                unsigned short *odd = g_tex_odd + (even - g_tex_even);
                for (v = 0; v < TEX_SIZE; v++) {
                    int level = texel_level(material, u, v);
                    int pen;
                    if (shade && level > 0) level--;     /* the unlit face, one level down */
                    pen = PEN_FAMILY_BASE + material * PEN_FAMILY_LEVELS + level;
                    even[v] = (unsigned short)(pen * PAIR_EVEN_SCALE);
                    odd[v] = (unsigned short)(pen * PAIR_ODD_SCALE);
                }
            }
        }
    }
}

/* ---------------------------------------------------------------- the map --------------------- */
/* A grid of MAP_ROOM-sized rooms with a doorway in the middle of every wall — the shape a
 * Wolfenstein level actually has, and the shape the DDA's cost depends on. AN OPEN MAP IS THE
 * EXPENSIVE ONE: the loop steps once per grid line crossed, so a ray down a long empty hall costs
 * ten times one that hits the far side of a room, and a bench on an open map measures the map
 * rather than the renderer. Cell 0 is open; a non-zero cell selects a material.
 *
 * The doorways still line up across rooms, so some rays do travel the length of the map — which is
 * the honest worst case to have in the measurement rather than to design out of it. */
static void build_map(void)
{
    int x, y;
    for (y = 0; y < MAP_SIZE; y++) {
        for (x = 0; x < MAP_SIZE; x++) {
            int in_room_x = x % MAP_ROOM;
            int in_room_y = y % MAP_ROOM;
            int on_wall = (in_room_x == 0) || (in_room_y == 0);
            int in_doorway = (in_room_x == 0 && (in_room_y == MAP_DOOR_LOW || in_room_y == MAP_DOOR_HIGH))
                          || (in_room_y == 0 && (in_room_x == MAP_DOOR_LOW || in_room_x == MAP_DOOR_HIGH));
            unsigned char cell = 0;
            if (on_wall && !in_doorway) {
                cell = (unsigned char)(1 + ((x / MAP_ROOM + y / MAP_ROOM) & (TEX_COUNT - 1)));
            }
            if (x == 0 || y == 0 || x == MAP_SIZE - 1 || y == MAP_SIZE - 1) cell = 1;
            g_map[(y << MAP_SHIFT) + x] = cell;
        }
    }
}

/* ---------------------------------------------------------------- the camera ------------------ */
/* The viewpoint stands in the middle of a room, MAP_ROOM/2 from every wall of it, so the fixed
 * pass looks at a near wall and the rotating pass sweeps past two doorways. */
#define MAP_START_X             12
#define MAP_START_Y             12

static void set_angle(int angle)
{
    g_angle = (short)(angle & (BRAD_FULL - 1));
    g_dir_x = spike_sin[(g_angle + BRAD_QUARTER) & (BRAD_FULL - 1)];    /* cos */
    g_dir_y = spike_sin[g_angle];
    /* The camera plane is the direction turned a quarter, scaled by tan(FOV/2). */
    g_plane_x = (-g_dir_y * TAN_HALF_FOV_8_8) >> 8;
    g_plane_y = (g_dir_x * TAN_HALF_FOV_8_8) >> 8;
}

static long fixed_abs(long v)
{
    return v < 0 ? -v : v;
}

static long reciprocal(long magnitude)
{
    long index = magnitude >> RECIP_SHIFT;
    return spike_recip[index >= RECIP_ENTRIES ? RECIP_ENTRIES - 1 : index];
}

/* ---------------------------------------------------------------- the raycast ----------------- */
/* EVERY PRODUCT HERE IS 16x16, and these two spell that out to the assembler rather than hoping
 * the compiler infers it. The 68000's own MULU/MULS costs about 70 cycles; libgcc's 32x32
 * __mulsi3 costs about 250 plus the call, and it was a third of the raycast stage before this
 * change. GCC did narrow most of them from the C types alone — but not all, and the two it left
 * behind were in the DDA's hot path, so the instruction is named here instead. The bound each
 * caller relies on is stated where the call is made; none of them is close. */
static unsigned long mul16u(unsigned short a, unsigned short b)
{
    unsigned long product = a;
    __asm__ ("mulu.w %1,%0" : "+d"(product) : "dmi"(b));
    return product;
}

static long mul16s(short a, short b)
{
    long product = a;
    __asm__ ("muls.w %1,%0" : "+d"(product) : "dmi"(b));
    return product;
}

/* The ray directions across the view are an arithmetic progression: ray = dir + plane * camera(x)
 * and camera(x) is linear in x, so the whole sweep is one add per column instead of two multiplies.
 * The accumulator carries eight bits more than 16.16 so the step's truncation cannot drift the
 * far edge of the view off the field of view. */
static void setup_rays(int width)
{
    g_ray_step_x = (g_plane_x * 512L) / width;
    g_ray_step_y = (g_plane_y * 512L) / width;
    g_ray_start_x = (g_dir_x << 8) - (g_ray_step_x * (width - 1)) / 2;
    g_ray_start_y = (g_dir_y << 8) - (g_ray_step_y * (width - 1)) / 2;
}

/* A textbook grid DDA, all of it 16.16, walking a MAP POINTER rather than a pair of cell indices:
 * the step is then a constant add of 1 or MAP_SIZE and the loop never recomputes y * MAP_SIZE. */
static void raycast(int width)
{
    const unsigned char *origin = g_map + ((int)(g_pos_y >> FIX_BITS) << MAP_SHIFT)
                                        + (int)(g_pos_x >> FIX_BITS);
    /* How far the player stands from the next grid line each way, in 0.8 of a cell. Constant for
     * the frame, so the DDA's two seed multiplies get their small operand for free. */
    unsigned short back_x = (unsigned short)((g_pos_x & (FIX_ONE - 1)) >> 8);
    unsigned short back_y = (unsigned short)((g_pos_y & (FIX_ONE - 1)) >> 8);
    unsigned short ahead_x = (unsigned short)((FIX_ONE - (g_pos_x & (FIX_ONE - 1))) >> 8);
    unsigned short ahead_y = (unsigned short)((FIX_ONE - (g_pos_y & (FIX_ONE - 1))) >> 8);
    long accumulator_x = g_ray_start_x;
    long accumulator_y = g_ray_start_y;
    SpikeRay *out = g_rays;
    int x;

    for (x = 0; x < width; x++, out++) {
        long ray_x = accumulator_x >> 8;
        long ray_y = accumulator_y >> 8;
        long delta_x = reciprocal(fixed_abs(ray_x));    /* 16.16, at most RECIP_MAX */
        long delta_y = reciprocal(fixed_abs(ray_y));
        const unsigned char *cell = origin;
        long side_x, side_y, perp, wall_offset;
        int cell_step_x, cell_step_y, side = 0, steps, material = 1;
        int texture_x, height, top, clipped, rows;
        unsigned long tex_step;

        accumulator_x += g_ray_step_x;
        accumulator_y += g_ray_step_y;

        /* delta >> 8 is at most RECIP_MAX >> 8 == 16384 and the distance to the grid line at most
         * 256, so both seeds are 16x16. */
        cell_step_x = (ray_x < 0) ? -1 : 1;
        cell_step_y = (ray_y < 0) ? -MAP_SIZE : MAP_SIZE;
        side_x = (long)mul16u((ray_x < 0) ? back_x : ahead_x, (unsigned short)(delta_x >> 8));
        side_y = (long)mul16u((ray_y < 0) ? back_y : ahead_y, (unsigned short)(delta_y >> 8));

        for (steps = 0; steps < DDA_MAX_STEPS; steps++) {
            if (side_x < side_y) {
                side_x += delta_x;
                cell += cell_step_x;
                side = 0;
            } else {
                side_y += delta_y;
                cell += cell_step_y;
                side = 1;
            }
            material = *cell;
            if (material) break;
        }

        perp = (side == 0) ? side_x - delta_x : side_y - delta_y;
        if (perp < MIN_PERP_DIST) perp = MIN_PERP_DIST;

        /* Where along the wall face the ray landed, and hence which texture column. perp >> 8 is at
         * most 16384 and a ray component at most one, so this product is 16x16 as well. */
        wall_offset = (side == 0)
                    ? g_pos_y + mul16s((short)(perp >> 8), (short)(ray_y >> 8))
                    : g_pos_x + mul16s((short)(perp >> 8), (short)(ray_x >> 8));
        texture_x = (int)((wall_offset & (FIX_ONE - 1)) >> (FIX_BITS - 6));   /* * TEX_SIZE >> 16 */
        if ((side == 0 && ray_x > 0) || (side == 1 && ray_y < 0)) {
            texture_x = TEX_SIZE - 1 - texture_x;
        }

        height = spike_divu((unsigned long)(VIEW_H << 8), (unsigned short)(perp >> 8));
        if (height < 1) height = 1;
        top = (VIEW_H - height) / 2;
        clipped = top < 0 ? -top : 0;
        if (top < 0) top = 0;
        rows = height - clipped;
        if (top + rows > VIEW_H) rows = VIEW_H - top;
        tex_step = mul16u((unsigned short)(perp >> 8), TEX_STEP_PER_DIST) >> 8;

        out->top = (short)top;
        out->rows = (short)rows;
        out->tex_offset = (unsigned short)(((((material - 1) & (TEX_COUNT - 1)) * TEX_SHADES + side)
                                            * TEX_SIZE + texture_x) * TEX_COL_WORDS * 2);
        out->tex_step = tex_step;
        /* A clipped wall is a tall one, so its step is small: the product is 16x16 exactly when it
         * is not zero, which is what keeps this off __mulsi3 too. */
        out->tex_pos = clipped ? mul16u((unsigned short)clipped, (unsigned short)tex_step) : 0UL;
    }
}

/* ---------------------------------------------------------------- the band -------------------- */
/* The rows any wall reaches. Outside it the view is two flat colours, which the planar fill writes
 * at 2.6 cycles a byte instead of the chunky drawer's 26 a pixel plus the c2p's 31 — so the band is
 * where a raycaster on this machine wins or loses its frame rate. `banded == 0` forces the whole
 * view, which is the same frame drawn the other way and the reason both are measured. */
static void find_band(int width, int banded)
{
    int x;
    if (!banded) {
        g_band_top = 0;
        g_band_bottom = VIEW_H;
        return;
    }
    g_band_top = VIEW_H;
    g_band_bottom = 0;
    for (x = 0; x < width; x++) {
        int bottom = g_rays[x].top + g_rays[x].rows;
        if (g_rays[x].rows <= 0) continue;
        if (g_rays[x].top < g_band_top) g_band_top = g_rays[x].top;
        if (bottom > g_band_bottom) g_band_bottom = (short)bottom;
    }
    if (g_band_bottom <= g_band_top) {                  /* no wall anywhere: nothing to convert */
        g_band_top = 0;
        g_band_bottom = 0;
    }
}

/* ---------------------------------------------------------------- the stages ------------------ */
static void draw_columns(int width)
{
    SpikeDrawJob job;
    int pairs = width / 2;
    job.chunky = g_chunky + (long)g_band_top * pairs;
    job.rays = g_rays;
    job.tex_even = g_tex_even;
    job.tex_odd = g_tex_odd;
    job.pairs = (short)pairs;
    job.stride = (short)(pairs * 2);
    job.band_top = g_band_top;
    job.band_bottom = g_band_bottom;
    job.ceil_even = (unsigned short)(PEN_CEILING * PAIR_EVEN_SCALE);
    job.ceil_odd = (unsigned short)(PEN_CEILING * PAIR_ODD_SCALE);
    job.floor_even = (unsigned short)(PEN_FLOOR * PAIR_EVEN_SCALE);
    job.floor_odd = (unsigned short)(PEN_FLOOR * PAIR_ODD_SCALE);
    spike_draw_columns(&job);
}

static void solid_pattern(int pen, unsigned long *plane01, unsigned long *plane23)
{
    unsigned long plane[SCREEN_PLANES];
    int i;
    for (i = 0; i < SCREEN_PLANES; i++) plane[i] = ((pen >> i) & 1) ? 0xffffUL : 0UL;
    *plane01 = (plane[0] << 16) | plane[1];
    *plane23 = (plane[2] << 16) | plane[3];
}

#define SCREEN_LINES_PER_VIEW_ROW   (SCREEN_H / VIEW_H)
#define VIEW_ROW_BYTES              (SCREEN_LINES_PER_VIEW_ROW * SCREEN_BYTES_PER_LINE)

static void fill_bands(void)
{
    unsigned long plane01, plane23;
    solid_pattern(PEN_CEILING, &plane01, &plane23);
    spike_fill(g_screen, (long)g_band_top * VIEW_ROW_BYTES, plane01, plane23);
    solid_pattern(PEN_FLOOR, &plane01, &plane23);
    spike_fill(g_screen + (long)g_band_bottom * VIEW_ROW_BYTES,
               (long)(VIEW_H - g_band_bottom) * VIEW_ROW_BYTES, plane01, plane23);
}

static void convert(int width)
{
    int pairs = width / 2;
    const unsigned short *chunky = g_chunky + (long)g_band_top * pairs;
    unsigned char *screen = g_screen + (long)g_band_top * VIEW_ROW_BYTES;
    int rows = g_band_bottom - g_band_top;
    if (width == VIEW_W_HIGH) spike_c2p_high(chunky, screen, rows);
    else spike_c2p_low(chunky, screen, rows);
}

/* ---------------------------------------------------------------- a pass ---------------------- */
#define VIEWPOINT_START_ANGLE   16          /* looks down a corridor from the cleared start cell */

static void run_pass(int index)
{
    const short width = g_pass_plan[index].width;
    const short rotating = g_pass_plan[index].rotating;
    const short banded = g_pass_plan[index].banded;
    SpikePassLedger *out = &g_ledger.pass[index];
    int frame;

    out->columns = (unsigned long)width;
    out->rotating = (unsigned long)rotating;
    out->banded = (unsigned long)banded;
    for (frame = 0; frame < SPIKE_FRAMES_PER_PASS; frame++) {
        unsigned long t0, t1, t2, t3, t4;
        set_angle(VIEWPOINT_START_ANGLE + (rotating ? frame * ROTATE_STEP_BRAD : 0));
        t0 = spike_ticks();
        setup_rays(width);
        raycast(width);
        find_band(width, banded);
        t1 = spike_ticks();
        draw_columns(width);
        t2 = spike_ticks();
        fill_bands();
        t3 = spike_ticks();
        convert(width);
        t4 = spike_ticks();
        out->ticks_raycast += t1 - t0;
        out->ticks_columns += t2 - t1;
        out->ticks_fill += t3 - t2;
        out->ticks_c2p += t4 - t3;
        out->ticks_total += t4 - t0;
        out->band_top_sum += (unsigned long)g_band_top;
        out->band_bottom_sum += (unsigned long)g_band_bottom;
    }
}

/* ---------------------------------------------------------------- reporting ------------------- */
static char g_text[6144];

static char *put_str(char *p, const char *s)
{
    while (*s) *p++ = *s++;
    return p;
}

static char *put_num(char *p, unsigned long value)
{
    char digits[12];
    int n = 0;
    do { digits[n++] = (char)('0' + (value % 10)); value /= 10; } while (value);
    while (n) *p++ = digits[--n];
    return p;
}

static char *put_field(char *p, const char *label, unsigned long value)
{
    p = put_str(p, label);
    p = put_num(p, value);
    return p;
}

/* Per-frame microseconds from a pass total, computed frames-first so the product stays inside a
 * long: a whole pass in ticks times TIMER_TICK_NS would not. */
static unsigned long ticks_to_us(unsigned long ticks)
{
    return (ticks / SPIKE_FRAMES_PER_PASS) * TIMER_TICK_NS / 1000UL;
}

static char *put_pass(char *p, const SpikePassLedger *pass)
{
    unsigned long total_us = ticks_to_us(pass->ticks_total);
    p = put_field(p, "cols=", pass->columns);
    p = put_field(p, " rot=", pass->rotating);
    p = put_field(p, " band=", pass->banded);
    p = put_field(p, " ray=", ticks_to_us(pass->ticks_raycast));
    p = put_field(p, " col=", ticks_to_us(pass->ticks_columns));
    p = put_field(p, " fill=", ticks_to_us(pass->ticks_fill));
    p = put_field(p, " c2p=", ticks_to_us(pass->ticks_c2p));
    p = put_field(p, " tot=", total_us);
    p = put_field(p, " fps10=", total_us ? 10000000UL / total_us : 0UL);
    p = put_field(p, " bt=", pass->band_top_sum / SPIKE_FRAMES_PER_PASS);
    p = put_field(p, " bb=", pass->band_bottom_sum / SPIKE_FRAMES_PER_PASS);
    return put_str(p, "\r\n");
}

static void format_report(void)
{
    char *p = g_text;
    int i;
    p = put_str(p, "SPIKE raycast bench (times are MICROSECONDS PER FRAME, fps10 = fps * 10)\r\n");
    p = put_field(p, "frames=", g_ledger.frames);
    p = put_field(p, " tick_ns=", g_ledger.tick_ns);
    p = put_field(p, " timer_c_max=", g_ledger.timer_c_max);
    p = put_field(p, " ledger=", SPIKE_LEDGER_ADDR);
    p = put_field(p, " screen=", g_ledger.screen);
    p = put_str(p, "\r\n");
    for (i = 0; i < SPIKE_PASSES; i++) p = put_pass(p, &g_ledger.pass[i]);
    *p = '\0';
}

#define RESULT_FILENAME     "RESULT.TXT"
#define FCREATE_NORMAL      0

static void write_report_file(void)
{
    long handle = Fcreate(RESULT_FILENAME, FCREATE_NORMAL);
    long length = 0;
    if (handle < 0) return;
    while (g_text[length]) length++;
    Fwrite((short)handle, length, g_text);
    Fclose((short)handle);
}

/* ---------------------------------------------------------------- the run --------------------- */
#define CURSOR_OFF          "\033f"
#define FRCLOCK_ADDR        0x466               /* TOS's VBL counter, supervisor-only */
#define HOLD_VBLS           120                 /* the still frame a debugger screenshot lands in */
#define TIMER_C_PROBE_READS 4000

/* The run's own check that this TOS programmed timer C the way TIMER_C_RELOAD assumes. A reload of
 * 192 can never be read back above 191; a larger maximum means the clock arithmetic is wrong and
 * every number in the ledger with it. */
static unsigned long probe_timer_c(void)
{
    unsigned long highest = 0;
    int i;
    for (i = 0; i < TIMER_C_PROBE_READS; i++) {
        unsigned long value = spike_timer_c_read();
        if (value > highest) highest = value;
    }
    return highest;
}

/* Publish both fixed-address blocks a longword at a time — NOT struct assignments, which the
 * compiler is free to turn into calls to memcpy, and this program links -nostdlib. The ledger's
 * magic goes down LAST and separately, so a debugger breakpoint on it means every field before it,
 * and the rays beside it, have landed.
 *
 * THE DESTINATIONS ARE `volatile` AND THAT IS A CORRECTNESS FIX, NOT A STYLE ONE. Each copy runs
 * between two addresses the compiler knows at build time, and GCC 16 folds that into ONE address
 * register:
 *      move.l (%a0)+,(d,%a0,%d0.l)          | d == destination - source
 * On the 68000 the source operand is fetched and %a0 post-incremented BEFORE the destination's
 * effective address is calculated, so every longword lands four bytes too high and the whole
 * published block is shifted by one slot — measured under Hatari on 2026-08-27, with the ledger's
 * magic at the right address and every field after it one late, which reads as a struct-layout
 * disagreement rather than as a code generation fault. `volatile` on the destination stops the
 * fusion — `volatile` alone does NOT, because the fold is a choice of addressing mode and GCC
 * still considers the single store it emits to be the one the source asked for. */
static volatile unsigned long *opaque_block(unsigned long address)
{
    volatile unsigned long *block = (volatile unsigned long *)address;
    __asm__ ("" : "+a"(block));       /* ...the value is now unknown to the optimiser */
    return block;
}

static void publish_rays(void)
{
    volatile unsigned long *out = opaque_block(SPIKE_RAYS_ADDR);
    const unsigned long *in = (const unsigned long *)g_rays;
    unsigned long i;
    for (i = 0; i < SPIKE_RAYS_BYTES / sizeof(unsigned long); i++) out[i] = in[i];
}

static void publish_ledger(void)
{
    volatile unsigned long *out = opaque_block(SPIKE_LEDGER_ADDR);
    const unsigned long *in = (const unsigned long *)&g_ledger;
    unsigned long i;
    for (i = 1; i < sizeof(SpikeLedger) / sizeof(unsigned long); i++) out[i] = in[i];
    out[0] = SPIKE_LEDGER_MAGIC;
}

static void render_showcase_frame(void);

/* Hold the showcase frame on screen, REDRAWING IT every pass rather than idling. Hatari's
 * `screenshot` hands back the last surface it RENDERED, and under --fast-forward that is not
 * necessarily the frame the debugger stopped on; were this an idle loop the captured picture could
 * be the last BENCHMARK frame, a different angle at a different column count from the rays
 * published beside it. Redrawing makes every frame in the window the same one.
 *
 * TOS's low RAM really does live at address 0x466, and GCC's -Warray-bounds cannot tell a machine
 * variable from a null-pointer dereference. The suppression is scoped to this one function so the
 * check keeps working everywhere else. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Warray-bounds"
static void hold_showcase(int vbls)
{
    volatile unsigned long *frclock = (volatile unsigned long *)FRCLOCK_ADDR;
    unsigned long until = *frclock + (unsigned long)vbls;
    while (*frclock < until) render_showcase_frame();
}
#pragma GCC diagnostic pop

static void render_showcase_frame(void)
{
    set_angle(VIEWPOINT_START_ANGLE);
    setup_rays(VIEW_W_HIGH);
    raycast(VIEW_W_HIGH);
    find_band(VIEW_W_HIGH, 1);
    draw_columns(VIEW_W_HIGH);
    fill_bands();
    convert(VIEW_W_HIGH);
}

int spike_main(void)
{
    void *ssp;
    int i;

    build_c2p_table(spike_c2p_table_high, C2P_POSITIONS_HIGH, SCREEN_W / VIEW_W_HIGH);
    build_c2p_table(spike_c2p_table_low, C2P_POSITIONS_LOW, SCREEN_W / VIEW_W_LOW);
    build_textures();
    build_map();
    g_pos_x = ((long)MAP_START_X << FIX_BITS) + FIX_ONE / 2;
    g_pos_y = ((long)MAP_START_Y << FIX_BITS) + FIX_ONE / 2;

    Cconws(CURSOR_OFF);
    g_screen = (unsigned char *)Physbase();

    ssp = (void *)Super(0);
    set_palette();
    g_ledger.version = SPIKE_LEDGER_VERSION;
    g_ledger.tick_ns = TIMER_TICK_NS;
    g_ledger.cpu_hz = ST_CPU_HZ;
    g_ledger.frames = SPIKE_FRAMES_PER_PASS;
    g_ledger.passes = SPIKE_PASSES;
    g_ledger.screen = (unsigned long)g_screen;
    g_ledger.timer_c_max = probe_timer_c();
    for (i = 0; i < SPIKE_PASSES; i++) run_pass(i);
    /* THE SHOWCASE FRAME IS HELD ON SCREEN *BEFORE* THE LEDGER IS PUBLISHED, and the order is part
     * of the measurement. The debugger script fires on the ledger's magic and Hatari's screenshot
     * hands back the last surface RENDERED; publishing first meant the capture caught whichever
     * benchmark frame the emulator had drawn last — a different angle at a different column count
     * from the rays published beside it, a picture disagreeing with its own data for no reason but
     * this ordering. Holding first makes every recently drawn frame the showcase one. */
    hold_showcase(HOLD_VBLS);
    publish_rays();
    publish_ledger();
    spike_leave_supervisor(ssp);

    format_report();
    write_report_file();
    Cconws(g_text);
    return 0;
}
