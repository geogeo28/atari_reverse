/* ym_music.h — a 3-channel YM2149 music replayer, stepped once per 50 Hz VBL.
 *
 * SOFTWARE ENVELOPES ONLY. Every amplitude this driver produces comes from a per-frame volume
 * table written into PSG registers 8-10; the YM's own envelope generator (registers 11-13, and
 * bit 4 of a volume register) is never armed. That is the classic ST chip-tune approach and it is
 * also what makes a channel's level predictable enough for an SFX to steal it and hand it back.
 *
 * WHO MAY CALL WHAT. Every entry point below EXCEPT `ym_music_sfx_play` writes the PSG, which is
 * supervisor-only space: call them from the VBL (this build installs the tick on the _vblqueue, see
 * audiotest.c) or under Supexec, never from plain user code. `ym_music_sfx_play` writes no hardware
 * and executes no privileged instruction, so it is callable from anywhere, user mode included.
 *
 * The song blob is a read-only image the caller owns (linked in, or Fread into a buffer) — the
 * driver keeps a pointer to it and never writes through it. Its layout is mk_song.py's docstring.
 * IT MUST START ON AN EVEN ADDRESS: one field is read as a 16-bit word every frame, and an odd
 * buffer would be an address error rather than a wrong note. ym_music_init refuses one.
 */
#ifndef YM_MUSIC_H
#define YM_MUSIC_H

#include <stdint.h>

#define YM_CHANNEL_COUNT 3
#define YM_NOTE_COUNT   96      /* semitone index 0 = C-1 (32.7 Hz); see ym_notes.h */

/* Bind the driver to a song image `bytes` long. Returns 0 (and leaves the driver stopped) when the
 * blob is not a song this driver understands, so a caller can refuse to run rather than play noise.
 *
 * `bytes` IS THE POINT OF THIS CALL, not a convenience. Every offset in the format is a 16-bit
 * field inside the blob, and the tick follows them with no checking at all — a truncated Fread, a
 * blob the linker placed short, or a byte flipped in a table offset would send the sequencer
 * reading a pattern from somewhere else in the program's memory and playing whatever it decoded.
 * ym_music_init walks the whole structure ONCE against this length — the order, every pattern,
 * every instrument's two tables, the SFX macros — and refuses the blob if anything falls outside
 * it, which is what buys the tick the right to be unchecked. The generators emit the length beside
 * the array (DEMO_SONG_BYTES, BLACKICE_SCORE_BYTES, ...), so a caller has no number to invent. */
int ym_music_init(const void *song_blob, uint32_t bytes);

/* Rewind to the first entry of the sequence and start stepping rows on the next tick. */
void ym_music_start(void);

/* Stop the sequencer and leave the PSG silent: all three tone/noise mixer bits off, all three
 * volumes 0. This is the teardown state, safe to leave the machine in for TOS. */
void ym_music_stop(void);

/* One frame of the driver: step the sequencer, advance every channel's tables, write the PSG. */
void ym_music_tick(void);

/* Change the tempo of the song that is already playing, WITHOUT restarting it: `frames_per_row`
 * replaces the value ym_music_init read out of the blob header, and the row the sequencer is on
 * finishes at the old rate. A 0 is ignored, because a song with no frames per row would step the
 * sequencer forever on one tick.
 *
 * This is the whole of BLACK ICE's trace-meter escalation (DESIGN.md 16: "the tempo IS the trace
 * meter", "tempo change is a driver counter, not a new module") — four bands are one song blob and
 * four calls to this, not four blobs. Callable wherever ym_music_tick is: it writes no hardware,
 * but it races the tick, so call it from the VBL or under Supexec. */
void ym_music_set_speed(uint16_t frames_per_row);

/* Steal the SFX channel for the short instrument+note macro `sfx_index` names in the song blob.
 * Returns 1 if the macro was accepted, 0 if the index is out of range, the macro names an
 * instrument that cannot be played as one (see mk_song.py: a looping volume table would never
 * release the channel), or a HIGHER-priority macro is still sounding there. The channel returns to
 * the music when the macro's volume table runs out.
 *
 * IT IS A REQUEST, AND THE TICK PERFORMS IT — one aligned word stored into a pending slot, and
 * nothing else. That is what makes it safe to call from outside the vblank: the whole channel
 * update belongs to the tick, so a caller interrupted mid-update cannot exist, and the routine
 * needs no interrupt mask (which would be a privileged instruction, and this is callable from user
 * mode). The sound therefore starts on the NEXT tick, up to one frame — 20 ms at 50 Hz — after the
 * call. The RETURN VALUE is still decided here and now, against the channel as it stands, because
 * it is what a caller routes on.
 *
 * Two requests inside the same frame: the second wins, and if they name the same sound one of them
 * is dropped. Both are the honest answer to asking twice in 20 ms, and neither can corrupt the
 * driver — the caller's only write is that one word. */
int ym_music_sfx_play(uint8_t sfx_index);

#endif /* YM_MUSIC_H */
