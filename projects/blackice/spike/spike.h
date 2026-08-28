/* spike.h — every constant the C driver and the hand-written asm must agree on.
 *
 * render.S is compiled as a .S so cpp runs over it: this file is the ONE definition of the screen
 * geometry, the chunky-buffer layout, the c2p table shape and the SpikeColumn field offsets. A
 * value that lived twice (once in C, once as an asm literal) is exactly the kind of drift that
 * shows up as a rendered frame that is one word wide of the truth, so nothing here is duplicated.
 */
#ifndef SPIKE_H
#define SPIKE_H

/* ---------------------------------------------------------------- the machine ---------------- */
#define ST_CPU_HZ                   8000000L    /* nominal 8 MHz; PAL ST is 8.0106 MHz (see REPORT) */
#define SCREEN_W                    320
#define SCREEN_H                    200
#define SCREEN_PLANES               4
#define SCREEN_BYTES_PER_LINE       160         /* 16 px = 4 interleaved plane words = 8 bytes */
#define SCREEN_GROUP_BYTES          8           /* one 16-screen-pixel group, all four planes */
#define SCREEN_BYTES                (SCREEN_BYTES_PER_LINE * SCREEN_H)      /* 32000 */
#define GROUPS_PER_LINE             (SCREEN_BYTES_PER_LINE / SCREEN_GROUP_BYTES)  /* 20 */

/* MFP timer C is TOS's own 200 Hz tick; we read its down-counter for the sub-tick part. */
#define HZ_200_ADDR                 0x4ba       /* _hz_200, a long, supervisor-only */
#define TIMER_C_DATA_ADDR           0xfffffa23  /* MFP TCDR */
#define TIMER_C_RELOAD              192         /* 2457600 / 64 / 192 == 200 Hz exactly */
#define TIMER_TICK_NS               26042L      /* 64 / 2457600 s, rounded; see REPORT */

/* ---------------------------------------------------------------- the render window ----------- */
/* 160x100 logical pixels pixel-doubled to 320x200, or 80x100 (4 px wide) as the low-detail fallback. */
#define VIEW_H                      100
#define VIEW_W_HIGH                 160
#define VIEW_W_LOW                  80
#define VIEW_PAIRS_HIGH             (VIEW_W_HIGH / 2)   /* 80 */
#define VIEW_PAIRS_LOW              (VIEW_W_LOW / 2)    /* 40 */
#define CHUNKY_STRIDE_HIGH          (VIEW_PAIRS_HIGH * 2)   /* bytes per logical row */
#define CHUNKY_STRIDE_LOW           (VIEW_PAIRS_LOW * 2)
#define CHUNKY_WORDS                (VIEW_PAIRS_HIGH * VIEW_H)

/* ---------------------------------------------------------------- chunky <-> planar ----------- */
/* THE CHUNKY BUFFER HOLDS ONE WORD PER PIXEL *PAIR*, and the word is already the c2p table's byte
 * offset: pair = even*16 + odd, offset = pair * C2P_ENTRY_BYTES. The even column of a pair writes
 * the word (`move.w`), the odd column ORs into it (`or.w`), so no clear pass is needed and the c2p
 * does ONE table lookup per two logical pixels instead of two. That is why the textures are stored
 * pre-scaled twice (PAIR_EVEN_SCALE and PAIR_ODD_SCALE): the drawer never shifts. */
#define C2P_ENTRY_BYTES             8       /* planes 0/1 long at +0, planes 2/3 long at +4 */
#define C2P_PLANE23_OFF             4
#define C2P_PAIR_COUNT              256
#define C2P_TABLE_BYTES             (C2P_PAIR_COUNT * C2P_ENTRY_BYTES)      /* one position */
#define C2P_POSITIONS_HIGH          4       /* 4 pairs == 8 logical px == one 16-px screen group */
#define C2P_POSITIONS_LOW           2       /* 2 pairs == 4 logical px == one 16-px screen group */
#define PAIR_ODD_SCALE              C2P_ENTRY_BYTES         /* 8   */
#define PAIR_EVEN_SCALE             (16 * C2P_ENTRY_BYTES)  /* 128 */

/* ---------------------------------------------------------------- textures -------------------- */
/* Stored COLUMN-major (tex[column][row]) so a wall column is contiguous, and pre-scaled into the
 * two pair positions. TEX_SIZE is a power of two so the raycaster's texture coordinate masks. */
#define TEX_SIZE                    64
#define TEX_COUNT                   4
#define TEX_SHADES                  2       /* 0 = lit (N/S faces), 1 = dark (E/W faces) */
#define TEX_COLUMNS                 (TEX_COUNT * TEX_SHADES * TEX_SIZE)
#define TEX_COL_WORDS               TEX_SIZE
#define TEX_WORDS                   (TEX_COLUMNS * TEX_COL_WORDS)

/* ---------------------------------------------------------------- the map --------------------- */
#define MAP_SIZE                    64
#define MAP_SHIFT                   6           /* MAP_SIZE == 1 << MAP_SHIFT */
#define MAP_CELLS                   (MAP_SIZE * MAP_SIZE)
#define MAP_ROOM                    8           /* a room's pitch: walls on the multiples of it */
#define MAP_DOOR_LOW                3           /* the two cells of a wall a doorway opens */
#define MAP_DOOR_HIGH               4

/* ---------------------------------------------------------------- fixed point ----------------- */
#define FIX_BITS                    16
#define FIX_ONE                     (1L << FIX_BITS)
#define BRAD_FULL                   1024        /* angle units in a full turn */
#define BRAD_QUARTER                (BRAD_FULL / 4)
#define FOV_DEGREES                 60
#define TAN_HALF_FOV_8_8            148         /* tan(30 deg) * 256, rounded; see gen_tables.py */
#define RECIP_SHIFT                 5
#define RECIP_ENTRIES               ((int)(FIX_ONE >> RECIP_SHIFT) + 1)     /* 2049 */
#define RECIP_MAX                   (64L * FIX_ONE)     /* clamp: longer than the map's diagonal */
#define ROTATE_STEP_BRAD            6           /* 6/1024 turn == 2.11 degrees per frame */
#define DDA_MAX_STEPS               96          /* the map is walled on every side, so this never fires */
#define MIN_PERP_DIST               (FIX_ONE / 16)  /* clamp: a wall in the player's face */

/* THE TEXTURE STEP IS A MULTIPLY, NOT A DIVIDE, and this constant is why. The wall's pixel height
 * is VIEW_H*256/dist and the step down the texture is TEX_SIZE*FIX_ONE/height, so the step is just
 * dist * TEX_SIZE * FIX_ONE / (VIEW_H*256) — linear in the distance. One __mulsi3 replaces a 32-bit
 * divide per column, and the integer division below TRUNCATES, which is what keeps the drawer's
 * "texel index stays inside the column" invariant: step * height <= TEX_SIZE * FIX_ONE exactly. */
#define TEX_STEP_PER_DIST           ((TEX_SIZE * FIX_ONE) / VIEW_H)

/* ---------------------------------------------------------------- palette --------------------- */
/* 16 pens: 4 black/ceiling/floor/white, then 4 texture families of 3 levels (dark, mid, light).
 * The dark wall variant is the same texture one level down inside its family — that is the
 * "nibble remap" that gives lit/unlit sides with only 16 pens on screen. */
#define PEN_CEILING                 1           /* pens 0 and 3 are black and white; see main.c */
#define PEN_FLOOR                   2
#define PEN_FAMILY_BASE             4
#define PEN_FAMILY_LEVELS           3
#define PALETTE_ADDR                0xffff8240L
#define PALETTE_PENS                16

/* ---------------------------------------------------------------- the ledger ------------------ */
/* A FIXED absolute address so a Hatari debugger script can `savebin` it without knowing where
 * GEMDOS put us: 0x80000 is inside our TPA (we never Mshrink), far above the BSS image and far
 * below the stack, which GEMDOS leaves just under the screen at the top of a 1 MB machine. */
#define SPIKE_LEDGER_ADDR           0x80000L
#define SPIKE_LEDGER_MAGIC          0x53504b45L /* 'SPKE' */
#define SPIKE_LEDGER_VERSION        1
#define SPIKE_PASSES                8
#define SPIKE_FRAMES_PER_PASS       32

/* The showcase frame's whole SpikeRay array, published beside the ledger so a host-side checker can
 * compare the target's own per-column answer against a float reference — the surface that says the
 * PICTURE is right, which no timing number does. The offset clears the ledger with room to spare. */
#define SPIKE_RAYS_OFFSET           0x400
#define SPIKE_RAYS_ADDR             (SPIKE_LEDGER_ADDR + SPIKE_RAYS_OFFSET)
#define SPIKE_RAYS_BYTES            (VIEW_W_HIGH * RAY_SIZEOF)

/* ---------------------------------------------------------------- SpikeRay ------------------- */
/* One raycast column's answer, laid out for the ASM drawer that walks the array: 16 bytes so the
 * step is a shift, the texture offset already in bytes so the drawer never multiplies, and the two
 * longwords last so they stay longword-aligned. The offsets are asm-visible and pinned against the
 * C struct with _Static_assert in main.c. */
#define RAY_TEX_OFFSET              0       /* unsigned short, bytes from the shade's texture base */
#define RAY_TOP                     2       /* short, first logical row of the wall */
#define RAY_ROWS                    4       /* short, wall rows after clipping to the view */
#define RAY_TEX_POS                 8       /* unsigned long, 16.16 */
#define RAY_TEX_STEP                12      /* unsigned long, 16.16 */
#define RAY_SIZEOF                  16

/* ---------------------------------------------------------------- SpikeDrawJob ---------------- */
/* THE WHOLE COLUMN LOOP IS IN ASM, and this is why: with the band optimisation a column is only a
 * dozen pixels tall, so a per-column C call — struct fill, argument push, prologue — cost about ten
 * times the pixels it drew (measured: 1680 cycles a column for 13 pixels, 2026-08-27). One job
 * describes all of them and the asm walks the SpikeRay array itself. */
#define DRAW_CHUNKY                 0       /* unsigned short *, band_top's row, pair 0 */
#define DRAW_RAYS                   4       /* const SpikeRay * */
#define DRAW_TEX_EVEN               8       /* const unsigned short *, texels * PAIR_EVEN_SCALE */
#define DRAW_TEX_ODD                12
#define DRAW_PAIRS                  16      /* short, columns / 2 */
#define DRAW_STRIDE                 18      /* short, chunky bytes per logical row */
#define DRAW_BAND_TOP               20      /* short */
#define DRAW_BAND_BOTTOM            22      /* short */
#define DRAW_CEIL_EVEN              24      /* unsigned short, already pair-scaled */
#define DRAW_CEIL_ODD               26
#define DRAW_FLOOR_EVEN             28
#define DRAW_FLOOR_ODD              30
#define DRAW_SIZEOF                 32

/* ---------------------------------------------------------------- fill ------------------------ */
/* spike_fill writes 40 bytes per MOVEM (ten registers), so its byte count must be a multiple of 40.
 * Every region it is asked for is a whole number of screen lines (160 bytes), so it always is. */
#define FILL_CHUNK_BYTES            40

#endif /* SPIKE_H */
