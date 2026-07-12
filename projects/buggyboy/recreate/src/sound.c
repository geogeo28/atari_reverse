/* sound.c — sound-driver leaves used by the course-event engine.
 *
 * TURNOFF/INITFX/INITTUNE set up the driver's per-voice music/effect state (the block at
 * SND_STATE and the voice-control records at SND_VOICE_CTRL) from const parameter tables. The
 * block's individual field *meanings* are only partly reversed, so its fields are named by
 * offset+role; the differential test against the oracle is what guarantees the reconstruction is
 * exact. These routines are pure (no OS traps, no further calls) — the driver runs from the VBL.
 */
#include "machine.h"
#include "addrs.h"
#include "buggyboy.h"

#define SND_STATE      0x1b05c   /* driver state block (music header + effect voice) */
#define SND_FX_TABLE   0x1bc56   /* const: per-effect parameter records */
#define SND_TUNE_TAB_B 0x1b5f3   /* const: per-tune byte parameter */
#define SND_TUNE_TAB_W 0x1b5f4   /* const: per-tune word parameters (3 per tune) */
#define SND_VOICE_CTRL 0x1b64a   /* three voice-control records */

/* SND_STATE field offsets (A_mzflag / A_fxflag are the same block at +0x1e / +0x1f). */
#define SND_MUSIC_BYTE 0x07      /* TURNOFF clears these two (music-playing state) */
#define SND_MUSIC_WORD 0x08
#define SND_FX_PRE_LO  0x0a      /* two words below the effect params (record words 7,8) */
#define SND_FX_PRE_HI  0x0c
#define SND_FX_PARAMS  0x0e      /* SND_FX_WORDS-word effect parameter block */
#define SND_FX_REREAD  0x18      /* param word re-read into SND_FX_TAIL */
#define SND_FX_TAIL    0x1c
#define SND_TUNE_LEN   0x24      /* INITTUNE music header: length (=SND_TUNE_LEN_VAL) */
#define SND_TUNE_PARAM 0x25      /*                        per-tune byte */
#define SND_TUNE_ON    0x26      /*                        active flag (=0xff) */

#define SND_FX_RECORD  0x12      /* per-effect record size (mulu factor) */
#define SND_FX_WORDS   7         /* effect words copied into SND_FX_PARAMS */
#define SND_TUNE_LEN_VAL 6       /* value written to the music-header length field */

/* Voice-control record layout (SND_VOICE_CTRL[voice], stride SND_VOICE_STRIDE). */
#define SND_VOICES        3
#define SND_VOICE_STRIDE  0x18
#define SND_VC_STATE   0x00      /* voice state word (=SND_VC_STATE_VAL) */
#define SND_VC_PTR     0x02      /* = SND_STATE[param] */
#define SND_VC_PARAM   0x04      /* = per-tune word */
#define SND_VC_ENABLE  0x0a      /* enable byte (=1) */
#define SND_VC_RESET   0x13      /* reset byte (=0) */
#define SND_VC_STATE_VAL  2
#define SND_TUNE_STEP     2      /* per-voice advance through the tune word table (addq.b #2) */

/* TURNOFF @0x1b268 — stop music: clear the music-active byte/word and MZFLAG. */
void g_TURNOFF(uint8_t *image) {
    image[A_mzflag] = 0;
    image[SND_STATE + SND_MUSIC_BYTE] = 0;
    wr16(image + SND_STATE + SND_MUSIC_WORD, 0);
}

/* INITFX @0x1b560 — load effect D0's parameter record into the effect voice state. */
void g_INITFX(uint8_t *image, uint32_t fx_id) {
    uint16_t idx = (uint16_t)(int16_t)(int8_t)fx_id;         /* ext.w d0 */
    uint16_t prod = (uint16_t)(idx * SND_FX_RECORD);         /* mulu.w #0x12 (low word) */
    uint32_t src = SND_FX_TABLE + sign_ext16(prod);          /* adda.w d0, a0 */

    image[A_fxflag] = 0;
    for (int i = 0; i < SND_FX_WORDS; i++)
        wr16(image + SND_STATE + SND_FX_PARAMS + 2 * i, be16(image + src + 2 * i));
    wr16(image + SND_STATE + SND_FX_PRE_LO, be16(image + src + SND_FX_WORDS * 2));       /* word 7 */
    wr16(image + SND_STATE + SND_FX_PRE_HI, be16(image + src + SND_FX_WORDS * 2 + 2));   /* word 8 */
    wr16(image + SND_STATE + SND_FX_TAIL, be16(image + SND_STATE + SND_FX_REREAD));
    image[A_fxflag] = 0xff;
}

/* INITTUNE @0x1b59c — start music track D0: seed the music header and the three voice-control
 * records from the per-tune tables, then flag music active. */
void g_INITTUNE(uint8_t *image, uint32_t tune_id) {
    uint16_t d0 = (uint16_t)(int16_t)(int8_t)tune_id;        /* ext.w d0 */
    uint16_t idx = set_low_byte(d0, (uint8_t)(d0 << 3));     /* asl.b #3 (8-byte tune stride) */

    image[A_mzflag] = 0;
    image[SND_STATE + SND_TUNE_LEN] = SND_TUNE_LEN_VAL;
    image[SND_STATE + SND_TUNE_ON] = 0xff;
    image[SND_STATE + SND_TUNE_PARAM] = image[SND_TUNE_TAB_B + idx];

    uint32_t rec = SND_VOICE_CTRL;
    uint16_t cur = idx;                                      /* d0.w indexes the word table */
    for (int voice = 0; voice < SND_VOICES; voice++) {
        uint16_t param = be16(image + SND_TUNE_TAB_W + cur);
        cur = set_low_byte(cur, (uint8_t)(cur + SND_TUNE_STEP));          /* addq.b #2, d0 */
        image[rec + SND_VC_ENABLE] = 1;
        wr16(image + rec + SND_VC_STATE, SND_VC_STATE_VAL);
        image[rec + SND_VC_RESET] = 0;
        wr16(image + rec + SND_VC_PARAM, param);
        wr16(image + rec + SND_VC_PTR, be16(image + SND_STATE + param));
        rec += SND_VOICE_STRIDE;
    }
    image[A_mzflag] = 0xff;
}