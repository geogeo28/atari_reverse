/* gemdos/fs_open.h — the GEMDOS leaves that FIND A NAME and act on its entry: the first search, the
 * current directory, opening, the attribute byte and deleting (`src/gemdos/fs_open.c`).
 *
 *   $fc6d14  gemdos_sfirst     a path's first match into a DTA, the search's state with it
 *   $fc6cf6  gemdos_fsfirst    ($4e) ...into the running process's DTA
 *   $fc6a7e  gemdos_dsetpath   ($3b) a path made a drive's current directory
 *   $fc7606  gemdos_open       a path's file opened into a handle
 *   $fc75f2  gemdos_fopen      ($3d) ...the same, as the leaf
 *   $fc7678  gemdos_fattrib    ($43) a file's attribute byte, read or written in its entry
 *   $fc77b2  gemdos_fdelete    ($41) a path's file deleted
 *
 * Every one of them is `$fc696c` (the path's directory) then `$fc663c` (the name in it), over the
 * directory layer (`include/gemdos/fs_dir.h`, which names the attributes a name is searched under),
 * the record layer and the file layer.
 */
#ifndef TOS102US_GEMDOS_FS_OPEN_H
#define TOS102US_GEMDOS_FS_OPEN_H

#include <stdint.h>

uint32_t gemdos_sfirst(uint8_t *image, uint32_t name, uint16_t attr, uint32_t dta);
uint32_t gemdos_fsfirst(uint8_t *image, uint32_t name, uint16_t attr);
uint32_t gemdos_dsetpath(uint8_t *image, uint32_t path);
uint32_t gemdos_open(uint8_t *image, uint32_t name, uint16_t mode);
uint32_t gemdos_fopen(uint8_t *image, uint32_t name, uint16_t mode);
uint32_t gemdos_fattrib(uint8_t *image, uint32_t name, uint16_t set, uint16_t attribute);
uint32_t gemdos_fdelete(uint8_t *image, uint32_t name);

#endif /* TOS102US_GEMDOS_FS_OPEN_H */
