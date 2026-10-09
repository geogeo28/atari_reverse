/* aes/deskmem.h — THE DESK'S MEMORY (`src/aes/deskmem.c`): what sh_main (`$feb0e6`) allocates before it runs the
 * desk and frees after it, and the count gem_entry clears THEGLO by.
 *
 *   $fee800 size_theglo()   5387: THEGLO's words less one — the `dbmi` count gem_entry's clear takes ($fd9f72..82)
 *   $fee80a desk_alloc()    five Malloc blocks through dos_alloc: the desk's globals (cleared), three more of the
 *                           desk's, and the G_USERDEF stack, whose TOP is what is kept
 *   $fee870 desk_free()     the two blocks the desk's globals name, the desk's resource (its rsrc_free binding: a
 *                           YIELD inside), then desk_alloc's five
 *
 * ALCYON C (size_theglo is called by `jsr`, the others by Line-F), over no argument.
 *
 * WHAT THE THREE OTHER BLOCKS ARE is the desk's to say (band 6): they are named here by their size alone.
 */
#ifndef TOS102US_AES_DESKMEM_H
#define TOS102US_AES_DESKMEM_H

#include <stdint.h>

#include "aes/aes.h"

/* ---- desk_alloc's blocks ------------------------------------------------------------------------------------------- */
#define DESK_GLOBALS_BYTES    19094      /* the desk's globals                  ($fee80e move.l #19094,(sp))   */
#define AES_DESK_BLOCK_512    0xc82e     /* long                                ($fee834 move.l d0,$c82e)      */
#define DESK_BLOCK_512_BYTES  512        /* ($fee82c move.l #512,(sp))                                         */
#define AES_DESK_BLOCK_920    0xc85e     /* long                                ($fee842 move.l d0,$c85e)      */
#define DESK_BLOCK_920_BYTES  920        /* ($fee83a move.l #920,(sp))                                         */
#define AES_DESK_BLOCK_16000  0xc67a     /* long                                ($fee850 move.l d0,$c67a)      */
#define DESK_BLOCK_16000_BYTES 16000     /* ($fee848 move.l #16000,(sp))                                       */
/* The G_USERDEF stack (`AES_USERDEF_STACK`, which ub_trampoline switches to): the block's END is kept. */
#define USERDEF_STACK_BYTES   1024       /* ($fee856 move.l #1024,(sp); $fee864 addi.l #1024,$8c3a)            */

/* ---- the two blocks the DESK allocated itself, which desk_free frees for it: pointers in its globals -------------- */
#define DESK_G_FIRST_FREED    14206      /* long                                ($fee87a move.l 14206(a0),(sp)) */
#define DESK_G_SECOND_FREED   14202      /* long                                ($fee886 move.l 14202(a0),(sp)) */

#ifndef __ASSEMBLER__
uint16_t aes_size_theglo(void);                                                                       /* $fee800 */
void aes_desk_alloc(uint8_t *image);                                                                  /* $fee80a */
void aes_desk_free(uint8_t *image);                                                                   /* $fee870 */
#endif

#endif /* TOS102US_AES_DESKMEM_H */
