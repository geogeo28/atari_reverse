/* gemdos/console.h — GEMDOS's fifteen character-device leaves, for the dispatcher that calls them.
 *
 * `src/gemdos/console.c` is selectors $01..$0b and $10..$13. Each is an ordinary Alcyon C routine
 * with its arguments on the stack, so the GEMDOS dispatcher reaches it with a plain `jsr` and these
 * declarations are what let the compiler check that call. Nothing else in the file is declared —
 * `include/xbios/xbios.h`'s rule: what crosses a translation unit, and no inventory.
 *
 * `entry_d0` IS AN ARGUMENT to the two that can return without writing D0 at all: `Cconws` over an
 * EMPTY string makes no call and touches nothing, and `Cconrs`' result is a `move.w d5,d0` whose
 * high half is whatever the caller arrived with. The other thirteen always end in a call that sets
 * the whole register, so they do not take it.
 *
 * THE STANDARD HANDLE IS NOT AN ARGUMENT EITHER, for any of them: each leaf reads its own out of
 * the running process's basepage (`GEMDOS_P_RUN`, `BASEPAGE_HANDLES`) and adds three. That is why a
 * `Cconout` is `(image, character)` and not `(image, device, character)`.
 */
#ifndef TOS102US_GEMDOS_CONSOLE_H
#define TOS102US_GEMDOS_CONSOLE_H

#include <stdint.h>

/* ---- input ($fc8ff2, $fc8faa, $fc900c, $fc903e) ------------------------------------------------ */

/* Cconin ($01): one character off stdin, ECHOED back to it, blocking. The whole longword the BIOS
 * left is the result — the IKBD's scancode half included. */
uint32_t gemdos_cconin(uint8_t *image);

/* Crawcin ($07): the same read with no echo and no ^C. */
uint32_t gemdos_crawcin(uint8_t *image);

/* Cnecin ($08): no echo either, but the typeahead poll afterwards, so ^C and ^S still bite. */
uint32_t gemdos_cnecin(uint8_t *image);

/* Cauxin ($03): straight to `Bconin` on the AUX device — no typeahead queue, no echo. */
uint32_t gemdos_cauxin(uint8_t *image);

/* ---- output ($fc8e1c, $fc8ed2, $fc8efa, $fc90c2) ----------------------------------------------- */

/* Cconout ($02): one character to stdout with TAB expanded to the next multiple of eight. */
uint32_t gemdos_cconout(uint8_t *image, uint16_t character);

/* Cauxout ($04) / Cprnout ($05): straight to `Bconout` — no tabs, no column, no typeahead poll. */
uint32_t gemdos_cauxout(uint8_t *image, uint16_t character);
uint32_t gemdos_cprnout(uint8_t *image, uint16_t character);

/* Cconws ($09): a NUL-terminated string to stdout, each byte SIGN-EXTENDED into the character
 * word — see the file's own note on what that does to a byte with bit 7 set. */
uint32_t gemdos_cconws(uint8_t *image, uint32_t entry_d0, uint32_t string);

/* ---- the two that are both ($fc9062, $fc91ea) -------------------------------------------------- */

/* Crawio ($06): `$00ff` reads stdin if a character is waiting (and answers 0 if none is); anything
 * else is written to stdout. Neither direction echoes and neither looks at the typeahead queue's
 * flow control. */
uint32_t gemdos_crawio(uint8_t *image, uint16_t character);

/* Cconrs ($0a): a whole edited line into a length-prefixed buffer — `buffer[0]` in, `buffer[1]` out,
 * the characters from `buffer[2]`. */
uint32_t gemdos_cconrs(uint8_t *image, uint32_t entry_d0, uint32_t buffer);

/* ---- status ($fc8b70, $fc8b8a, $fc8bae, $fc8bd2, $fc8bee) -------------------------------------- */

/* Cconis ($0b) / Cauxis ($12): is there a character waiting? A record in GEMDOS's own typeahead
 * queue counts, which is what makes these more than `Bconstat`. */
uint32_t gemdos_cconis(uint8_t *image);
uint32_t gemdos_cauxis(uint8_t *image);

/* Cconos ($10) / Cprnos ($11) / Cauxos ($13): can the device take another character? Each is
 * `Bcostat` on its own standard handle and nothing else. */
uint32_t gemdos_cconos(uint8_t *image);
uint32_t gemdos_cprnos(uint8_t *image);
uint32_t gemdos_cauxos(uint8_t *image);

/* ---- the layer under them, as the DISPATCHER reaches it ($fc8fc6, $fc9226, $fc8e3c) ------------ */

/* The dispatcher serves an `Fread`/`Fwrite` on a character-device handle itself, through these: one
 * record read and echoed RAW; an edited line of up to `maximum` characters into `line` (its length in
 * the low word, over `entry_d0`'s high half); one character out with TAB expanded; and `Bconout` through
 * the trampoline, parking `return_site` — the call site's own address — as every BIOS call here does. */
uint32_t gemdos_device_get_echoing(uint8_t *image, uint16_t device);
uint32_t gemdos_device_read_line(uint8_t *image, uint32_t entry_d0, uint16_t device, uint16_t maximum,
                                 uint32_t line);
uint32_t gemdos_device_put_expanding_tabs(uint8_t *image, uint16_t device, uint16_t character);
uint32_t gemdos_device_bconout(uint8_t *image, uint32_t return_site, uint16_t device, uint16_t character);

#endif /* TOS102US_GEMDOS_CONSOLE_H */
