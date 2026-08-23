/* tos.h — prototypes for the trap wrappers in wonderboy_os.s.
 *
 * The list is SHORT because the game is: ../project.toml's exhaustive byte scan of SWB.PRG finds
 * exactly one `trap` instruction in the whole image, a GEMDOS Super. Everything here beyond Super is
 * the SHIM's, not the game's — the file I/O that stages the image and writes the smoke's results,
 * and the three XBIOS calls the teardown uses to hand the machine back.
 */
#ifndef WONDERBOY_SHIM_TOS_H
#define WONDERBOY_SHIM_TOS_H

/* GEMDOS file I/O. Mostly the shim's own — but NOT all of it since batch 44 phase B:
 * wonderboy_backend.c's `disk_read_file` is the reconstruction's DISK SEAM, and it issues
 * Fopen/Fread/Fclose from this header on the game's behalf. That is the one place the port makes a
 * TOS call the original does not; see ../wonderboy_backend.c and ../../STATUS.md batch 44 phase B.
 * RETRACTION: until the seam landed this banner asserted that the reconstruction made no file call
 * whatsoever. That was true when written and is now false in exactly one place, named above. */
long Fcreate(const char *name, short attr);
long Fopen(const char *name, short mode);
long Fclose(short handle);
long Fread(short handle, long count, void *buf);
long Fwrite(short handle, long count, const void *buf);

/* GEMDOS control. `Super(0)` enters supervisor mode and hands back the SSP to restore; the way BACK
 * is `wb_leave_supervisor`, which is the same trap plus one privileged instruction. wonderboy_os.s
 * has the measurement that made the second routine necessary — in short, a plain `Super(ssp)`
 * returns onto the stack position the FIRST call stood at, and only luck keeps the two equal. */
long Super(void *stack);
long wb_leave_supervisor(void *ssp);

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
