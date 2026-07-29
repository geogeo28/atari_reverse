/* addrs.h — the Joust globals the reconstruction touches, by Ghidra address.
 *
 * Every address here is a Ghidra address (image offset + the 0x10000 load base fixed by
 * project.toml / PrgLoader) and mirrors a `var` line in ../../names.txt, which stays the source
 * of truth for the name.
 */
#ifndef JOUST_ADDRS_H
#define JOUST_ADDRS_H

#define IMAGE_LOAD_BASE 0x10000u   /* where the program image starts; some code holds addresses
                                    * into itself as relocated constants (see rng.c) */

#define A_screen_base   0x10ddeu   /* .l — base of the screen every draw routine addresses from */
#define A_rng_ptr       0x10dfeu   /* .l — the pseudo-random cursor walking the program image */

#endif /* JOUST_ADDRS_H */
