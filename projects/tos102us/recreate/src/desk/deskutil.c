/* deskutil.c — THE DESK'S UTILITIES (`desk/deskutil.h`), unit M: band 6 wave 2 lays it for group G2's two routines of
 * the cartridge's directory search (`$fed522`, `$fed534`). Alcyon C in the ROM, ported over its own order.
 */
#include "desk/deskutil.h"

/* ---- band 6 wave 2, group G2 (unit M) ---- */
#include <stdint.h>

#include "machine.h"
#include "aes/aes.h"
#include "aes/cart.h"
#include "aes/gemdosif.h"

/* $fed534 — cart_snext: the chain's next header laid into the kept DTA as a search's answer; at the chain's end,
 * AES_DOS_AX "no more files" — as dos_snext answers. */
int16_t aes_cart_snext(uint8_t *image)
{
    if (aes_cart_find(image, CART_SNEXT_FILL))
        return CART_SNEXT_FOUND;
    wr16(image + AES_DOS_AX, DOS_AX_NO_MORE_FILES);
    return CART_SNEXT_NONE;
}

/* $fed522 — cart_sfirst: the DTA kept for cart_find, the chain begun (cart_init), its first header searched for. The
 * attribute word its caller hands, as to dos_sfirst, is read by nothing. */
int16_t aes_cart_sfirst(uint8_t *image, uint32_t dta, int16_t unread)
{
    (void)unread;
    wr32(image + AES_CART_DTA, dta);
    (void)aes_cart_init(image);
    return aes_cart_snext(image);
}
/* ---- end of group G2's wave-2 ---- */
/* ---- band 6 wave 4, group G1 (unit M) ---- */
/* THE SHOW / PRINT ENGINE (`$fed61e..$fed887`): hand-shaped in the ROM — `$fed632` keeps its state in registers for
 * eight parts it reaches by `bsr` (D3 the handle, D4 the port, D5 the character, A3 the buffer, A6 the buffer's size AS
 * DATA) and in three words of RAM (`desk/deskglobals.h`'s AES_SHOW_*). Here the parts are static functions over that
 * state (ruling R-W4-5); the RAM words stay RAM. Three things the ROM does, reproduced:
 *   - no buffer: the engine returns with the file it opened still open;
 *   - the printer's alert reads its values pointer as $00000001 and its default button off the stack (deskutil.h);
 *   - a key whose ASCII is 0 does not end the viewer's wait (`tst.w`).
 */
#include "addrs.h"
#include "aes/fmdo.h"
#include "aes/gemstart.h"
#include "aes/strings.h"
#include "desk/deskbind.h"
#include "desk/deskdir.h"
#include "desk/deskglobals.h"
#include "desk/deskleaf.h"
#include "bios/bcon.h"
#include "gemdos/gemdos.h"

#ifdef RECREATE_HOST_DIFFERENTIAL
/* Setprt's core (`src/xbios/sound.c`), declared here because no header the host build sees declares it:
 * `xbios/xbios.h`, its natural home, is the target's (its inline traps). */
uint32_t xbios_setprt(uint8_t *image, uint32_t entry_d0, uint16_t config);
#endif

/* What the engine's parts read of its registers: the file and its buffer. (D5, the byte read, is next_byte's answer;
 * D4, the port, the print loop's own.) */
struct engine {
    int16_t handle;                      /* D3 */
    uint32_t buffer;                     /* A3 */
};
#define NO_BYTE               (-1)       /* next_byte's answer past the file (the ROM's D0 0, its D5 left)     */

/* gem_gemdos_call ($fd9fc6) AS THE ENGINE REACHES IT (`desk/deskleaf.h`'s two halves of its effect) — over a character
 * word (Cprnout, Cauxout) ... */
static uint32_t gemdos_called_with_a_word(uint8_t *image, uint32_t return_site, uint16_t function, uint16_t character)
{
    desk_gemdos_call_entered(image, return_site);
    return desk_gemdos_call_answered(image, gemdos_trap_word_word(image, function, character));
}

/* ...and over a string (Cconws) */
static void gemdos_called_with_a_string(uint8_t *image, uint32_t return_site, uint32_t text)
{
    desk_gemdos_call_entered(image, return_site);
    (void)desk_gemdos_call_answered(image, gemdos_trap_word_long(image, GEMDOS_CCONWS_FN, text));
}

/* Bconout(CON:, the character) through the ROM's trp13 door (`desk_bconout`: the three words the engine pushes) — not
 * through `aes_trp13`'s C twin, which lays the widest caller's six words for every call: a character at a time, it
 * priced the viewer's cases at 1.103-1.104 (the bar 1.10). */
static void console_out(uint8_t *image, uint16_t character)
{
    (void)desk_bconout(image, AES_SHOW_BCONOUT_RETURN, BCONOUT_CONSOLE, character);
}

/* Setprt(-1) through the ROM's trp14 door, over the two words the engine pushes as one longword: the printer's
 * configuration. ON TARGET the trap over that frame (`desk_xbios_trap`); OFF TARGET Setprt's own core. D0's high word
 * is read by nothing. */
static uint16_t printer_configuration(uint8_t *image)
{
    desk_xbios_parked(image, AES_SHOW_SETPRT_RETURN);
#ifdef RECREATE_HOST_DIFFERENTIAL
    return (uint16_t)xbios_setprt(image, 0, (uint16_t)SETPRT_ASK);
#else
    {
        const uint16_t frame[] = {XBIOS_SETPRT_FN, (uint16_t)SETPRT_ASK};

        return (uint16_t)desk_xbios_trap(frame, sizeof frame / sizeof frame[0]);
    }
#endif
}

/* $fed81a — a NUL-ended string written a character at a time through Crawio, each byte sign-extended to its word. */
static void rawcio_string(uint8_t *image, uint32_t text)
{
    for (; bus_byte(image, text); text++)
        (void)aes_dos_rawcio(image, AES_SHOW_STRING_RETURN, (int16_t)(int8_t)bus_byte(image, text));
}

/* A key awaited by Crawio($ff) until its answer's WORD is not 0: the key's ASCII and the byte above it. Never inlined:
 * its entry is where the viewer's chains stop on our shore (`test/aes_desk.py`'s OUR_STOPS_ONCE_FLIPPED). */
__attribute__((noinline)) static int16_t key_awaited(uint8_t *image, uint32_t return_site)
{
    int16_t key;

    do
        key = (int16_t)aes_dos_rawcio(image, return_site, CRAWIO_ASK);
    while (!key);
    return key;
}

/* $fed6d6 — the buffer's next byte, the buffer read again (Fread of all of it) where the index has run to its end;
 * NO_BYTE once the viewer showed the end, or where the index meets a short read's count. */
static int next_byte(uint8_t *image, const struct engine *engine)
{
    int16_t index = (int16_t)bus_word(image, AES_SHOW_INDEX);
    uint8_t byte;

    if (index == SHOW_INDEX_AT_THE_END)
        return NO_BYTE;
    if (index == (int16_t)bus_word(image, AES_SHOW_COUNT) && bus_word(image, AES_SHOW_AT_EOF))
        return NO_BYTE;
    if (index == SHOW_BUFFER_BYTES) {
        int16_t count;

        set_bus_word(image, AES_SHOW_INDEX, 0);
        count = (int16_t)aes_dos_read(image, engine->handle, SHOW_BUFFER_BYTES, engine->buffer);
        set_bus_word(image, AES_SHOW_COUNT, (uint16_t)count);
        if (count != SHOW_BUFFER_BYTES)
            set_bus_word(image, AES_SHOW_AT_EOF, SHOW_AT_EOF_SET);
        index = 0;
    }
    byte = bus_byte(image, engine->buffer + (uint32_t)(int32_t)index);
    set_bus_word(image, AES_SHOW_INDEX, (uint16_t)(index + 1));
    return byte;
}

/* $fed7cc — a line shown through Bconout, to its line feed (1); at the file's end CR LF and "-END OF FILE-" by Crawio,
 * the index made the end's (SHOW_INDEX_AT_THE_END) and 0. */
static int line_shown(uint8_t *image, const struct engine *engine)
{
    int byte;

    while ((byte = next_byte(image, engine)) != NO_BYTE) {
        console_out(image, (uint16_t)byte);
        if (byte == CON_LF)
            return 1;
    }
    (void)aes_dos_rawcio(image, AES_SHOW_END_CR_RETURN, CON_CR);
    (void)aes_dos_rawcio(image, AES_SHOW_END_LF_RETURN, CON_LF);
    rawcio_string(image, VIEWER_END);
    set_bus_word(image, AES_SHOW_INDEX, (uint16_t)SHOW_INDEX_AT_THE_END);
    return 0;
}

/* $fed7c0 — a page: lines until VIEWER_PAGE_LINES are shown or the file ends. */
static void page_shown(uint8_t *image, const struct engine *engine)
{
    int lines;

    for (lines = 0; lines < VIEWER_PAGE_LINES; lines++)
        if (!line_shown(image, engine))
            return;
}

/* $fed790 — "-MORE-", a key awaited and upcased, the line erased (Cconws): the key. */
static int16_t more_asked(uint8_t *image)
{
    int16_t key;

    rawcio_string(image, VIEWER_MORE);
    key = aes_toupper(key_awaited(image, AES_SHOW_MORE_KEY_RETURN));
    gemdos_called_with_a_string(image, AES_SHOW_ERASE_RETURN, VIEWER_ERASE_LINE);
    return key;
}

/* $fed736 — THE FILE VIEWER: wrap on, a page; then at each page's end "-MORE-" — Q or ^C ends it, a blank shows the
 * next page, Return the next line — and at the file's end a key ends it. */
static void viewer(uint8_t *image, const struct engine *engine)
{
    int done = 0;                        /* D7 */

    gemdos_called_with_a_string(image, AES_SHOW_WRAP_RETURN, VIEWER_WRAP_ON);
    page_shown(image, engine);
    do {
        if ((int16_t)bus_word(image, AES_SHOW_INDEX) == SHOW_INDEX_AT_THE_END) {
            (void)key_awaited(image, AES_SHOW_END_KEY_RETURN);
            done = 1;
        } else {
            int16_t key = more_asked(image);

            if ((uint8_t)key == VIEWER_QUIT || key == CON_ETX)
                done = 1;
            else if (key == VIEWER_NEXT_PAGE)
                page_shown(image, engine);
            else if (key == CON_CR)
                (void)line_shown(image, engine);
        }
    } while (!done);
}

/* $fed832 — the character to the RS232 port (Cauxout, done) or to the printer (Cprnout) — retried after its "not
 * ready" alert until printed, or abandoned (0) where the alert's answer is PRINTER_ALERT_CANCEL. The answer's word: 0
 * abandoned (a Cprnout answer of PRINT_ABANDONED reads as one too). */
static int16_t char_put(uint8_t *image, int to_the_printer, uint16_t character)
{
    int16_t printed;                     /* D6 */

    if (!to_the_printer) {
        (void)gemdos_called_with_a_word(image, AES_SHOW_CAUXOUT_RETURN, GEMDOS_CAUXOUT_FN, character);
        return PRINT_CHAR_DONE;
    }
    do {
        printed = (int16_t)gemdos_called_with_a_word(image, AES_SHOW_CPRNOUT_RETURN, GEMDOS_CPRNOUT_FN, character);
        if (printed)
            break;
        printed = aes_fm_show(image, PRINTER_ALERT_STRING, PRINTER_ALERT_VALUES, PRINTER_ALERT_DEFAULT)
                          == PRINTER_ALERT_CANCEL ? PRINT_ABANDONED : 0;
        aes_desk_wait(image, DESK_WAIT_BUSY);
    } while (!printed);
    return printed == PRINT_ABANDONED ? 0 : printed;
}

/* The file printed: a byte at a time, a key looked for before each — ^C or Q ends it, as does an abandoned byte —
 * then CR LF where the file ran out. */
static void printed(uint8_t *image, const struct engine *engine)
{
    int to_the_printer = !(printer_configuration(image) & SETPRT_RS232);     /* D4 */
    int byte;

    while ((byte = next_byte(image, engine)) != NO_BYTE) {
        int16_t key = aes_toupper((int16_t)aes_dos_rawcio(image, AES_SHOW_KEY_CHECK_RETURN, CRAWIO_ASK));

        if (key == CON_ETX || (uint8_t)key == VIEWER_QUIT || !char_put(image, to_the_printer, (uint16_t)byte))
            return;
    }
    (void)char_put(image, to_the_printer, CON_CR);
    (void)char_put(image, to_the_printer, CON_LF);
}

/* $fed632 — THE ENGINE: the file opened, a buffer taken, the file shown or printed, closed and the buffer given
 * back. */
static int16_t shown_or_printed(uint8_t *image, uint32_t name, int show)
{
    struct engine engine;

    set_bus_word(image, AES_SHOW_AT_EOF, 0);
    engine.handle = (int16_t)aes_dos_open(image, name, DOS_OPEN_READ);
    if (aes_dos_failed(image))
        return ENGINE_FAILED;
    engine.buffer = aes_dos_alloc(image, SHOW_BUFFER_BYTES);
    if (!engine.buffer)
        return ENGINE_FAILED;            /* the file left open: the ROM's */
    set_bus_word(image, AES_SHOW_INDEX, SHOW_BUFFER_BYTES);
    if (show)
        viewer(image, &engine);
    else
        printed(image, &engine);
    (void)aes_dos_close(image, AES_SHOW_CLOSE_RETURN, engine.handle);
    (void)aes_dos_free(image, AES_SHOW_FREE_RETURN, engine.buffer);
    return ENGINE_DONE;
}

/* $fed61e — desk_show_file: the engine over (name, ENGINE_SHOWS). */
int16_t aes_desk_show_file(uint8_t *image, uint32_t name)
{
    return shown_or_printed(image, name, ENGINE_SHOWS);
}

/* $fed624 — desk_print_file: ...over (name, ENGINE_PRINTS). */
int16_t aes_desk_print_file(uint8_t *image, uint32_t name)
{
    return shown_or_printed(image, name, ENGINE_PRINTS);
}
/* ---- end of group G1's wave-4 ---- */
