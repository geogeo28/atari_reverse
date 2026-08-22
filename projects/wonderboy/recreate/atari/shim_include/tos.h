/* tos.h — prototypes for the trap wrappers in wonderboy_os.s.
 *
 * The list is SHORT because the game is: ../project.toml's exhaustive byte scan of SWB.PRG finds
 * exactly one `trap` instruction in the whole image, a GEMDOS Super. Everything here beyond Super is
 * the SHIM's, not the game's — the file I/O that stages the image and writes the smoke's results,
 * and the three XBIOS calls the teardown uses to hand the machine back.
 */
#ifndef WONDERBOY_SHIM_TOS_H
#define WONDERBOY_SHIM_TOS_H

/* GEMDOS file I/O — the shim's own; the reconstruction makes no file call at all. */
long Fcreate(const char *name, short attr);
long Fopen(const char *name, short mode);
long Fclose(short handle);
long Fread(short handle, long count, void *buf);
long Fwrite(short handle, long count, const void *buf);

/* GEMDOS control. */
long Super(void *stack);

/* XBIOS. Physbase is the READ-BACK for what the shifter is displaying from; Setscreen is teardown
 * only, because it updates TOS's own `_v_bas_ad` as well as the shifter. */
long Physbase(void);
long Logbase(void);
void Setscreen(void *log, void *phys, short rez);

/* The two interrupt entries (wonderboy_os.s). Installed at the real exception vectors, as the boot
 * chain's `hw_init_vectors` ($f8bc) does. */
void wb_vbl_entry(void);
void wb_acia_entry(void);

/* Mask every interrupt and hand back the SR to restore. Supervisor only. Used for ONE critical
 * section — sampling the reconstruction's vblank counter and the shim's tick count at one instant,
 * which M1 compares — and wonderboy_os.s argues there why a retry loop cannot replace it. */
unsigned short wb_irq_disable(void);
void wb_irq_restore(unsigned short sr);

#endif /* WONDERBOY_SHIM_TOS_H */
