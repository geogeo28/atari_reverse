/* tos.h — the real TOS entry points the on-target build calls.
 *
 * Every one of these is a hand-written trap wrapper in joust_os.s; none is exercised by the
 * differential harness (the oracle services traps directly), so this file and that one are the
 * project's one wholly UNVERIFIED surface — see docs/on-target-execution.md §3.
 *
 * The C ABI passes every scalar in a 4-byte stack slot, so a `short` argument is the LOW word of
 * its slot on this big-endian machine; the wrappers all read the longword and push its low word.
 */
#ifndef JOUST_SHIM_TOS_H
#define JOUST_SHIM_TOS_H

/* GEMDOS (trap #1) */
long Super(void *stack);                                  /* 0x20 */
long Fcreate(const char *name, short attr);               /* 0x3c */
long Fopen(const char *name, short mode);                 /* 0x3d */
long Fclose(short handle);                                /* 0x3e */
long Fread(short handle, long count, void *buf);          /* 0x3f */
long Fwrite(short handle, long count, const void *buf);   /* 0x40 */
void Pterm(short code);                                   /* 0x4c — never returns */

/* BIOS (trap #13) */
long Bconstat(short dev);                                 /* 0x01 */
long Bconin(short dev);                                   /* 0x02 */

/* XBIOS (trap #14) */
void Setscreen(void *log, void *phys, short rez);         /* 0x05 */
long Random(void);                                        /* 0x11 */
void Ikbdws(short count_minus_one, const void *buf);      /* 0x19 */
long Giaccess(short data, short reg);                     /* 0x1c */
void Dosound(const void *list);                           /* 0x20 */
long Kbdvbase(void);                                      /* 0x22 */
void Vsync(void);                                         /* 0x25 */

/* joust_os.s: the IKBD joystick-packet handler installed at KBDVBASE joyvec, and the harmless
 * `rts` the mouse vector gets (the original installs its own two-instruction handlers there). */
void joy_handler(void);
void null_handler(void);

/* Globals joy_handler reads — it is entered off an interrupt, not the C ABI, so everything it
 * needs is a plain longword it can `move.l` (see joust_main.c for what each holds). */
extern unsigned char *joy_buf_addr;    /* real address of image + JOY_PACKET_BUF */
extern unsigned char *joy_slot_addr;   /* real address of image + A_ikbd_packet */
extern unsigned long joy_packet_off;   /* JOY_PACKET_BUF — the IMAGE OFFSET the cores dereference */

#endif /* JOUST_SHIM_TOS_H */
