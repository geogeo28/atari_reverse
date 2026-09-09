/* os_fs.c — the CANDIDATE side's copy of the staged-file window's base: where the table lives, and
 * with it the staging area a fixed distance above it. The mechanism that places it is in
 * ../README.md, "The staged-file window is the second region a project places"; the key that sets
 * it is `fs_base` in a project's project.toml, and the ORACLE keeps its own copy in oracle/shim.c.
 *
 * ON-TARGET builds compile none of this: without -DOS_FS_TABLE_RUNTIME os.h's OS_FS_TABLE is the
 * constant it always was, which is what a project's own .PRG build gets (it links no kit src/, so
 * an unconditional definition here would not reach it anyway).
 */
#include <stdint.h>

#include "os.h"

#ifdef OS_FS_TABLE_RUNTIME
/* The default is os.h's, so an unbound candidate — one nobody installed a base into — reads the
 * table exactly where every candidate read it before the key existed. */
uint32_t g_os_fs_table = OS_FS_TABLE_DEFAULT;

void os_set_fs_table(uint32_t base) { g_os_fs_table = base; }
#endif
