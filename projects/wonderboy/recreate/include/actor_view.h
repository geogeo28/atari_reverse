/* actor_view.h — deciding ONCE per actor what bus.h's field helpers decide once per FIELD.
 *
 * WHAT IT REPLACES. `field_w(image, actor, WB_ACTOR_X)` masks the address to 24 bits, bounds it
 * against the loaded image and only then indexes — three instructions ahead of the one the original
 * spells, `move.w d16(a0)`. src/behavior.c reaches an actor's own record 613 times, and at that
 * price a site it is the whole of the behaviour tier's x3.7 against the original (../STATUS.md,
 * "## Performance"). The guard is not wrong and it is not removable per access — the fast/slow arm
 * was written INTO bus.h and measured NO-GO on 2026-08-26, because both arms inline at every one of
 * ~800 sites and cost back more than they save. The decision has to be made once, for a whole
 * record, by whoever knows the record's address: the door a handler is entered through.
 *
 * FOUR MODULES OPEN DOORS THROUGH IT: src/behavior.c, src/map.c, src/player.c and src/actor.c —
 * the handlers, and the helpers those handlers call with a record they have already proved. bus.h is
 * the header for a record NOBODY has proved — src/scene.c and the five other modules still reach
 * every field that way, and so does this file for every record that is not the actor's own — and
 * this one is for a record somebody just did.
 *
 * HOW MANY DOORS THERE ARE IS DERIVED, NOT REMEMBERED, and this is the one place that says it —
 * every other file wanting the figure points here rather than carrying a second copy to drift:
 *
 *     grep -rc '^ACTOR_DOOR_' ../src       # 111: behavior.c 82, actor.c 12, player.c 10, map.c 7
 *
 * plus ONE door spelt out by hand, `launch_at_inline_speed` in include/actor.h, which is `static
 * inline` in a header and so cannot be a macro's extern definition. Eighty-four of the 111 are the
 * short `(image, actor)` forms and the rest carry parameters of their own.
 *
 * THE SLOW ARM AND THE ALL-LIVE MASK LIVE IN src/actor_view.c, one copy for the whole link, and
 * that is a decision with two reasons rather than a tidy-up. The arm must not be inlined — it is
 * reached by three cases in the suite and by no frame, and a copy of the fill and the give-back in
 * every one of those doors would spend the text this whole change is buying — and a `static` in the
 * header gave every including module its own copy of both, which `atari/profile.py` REFUSES
 * outright: it aggregates cycles by symbol name, and two symbols of one name would charge one with
 * the other's work. Only the two decisions that must inline are still here: `actor_view_open`'s
 * bound and the `rec_*` accessors.
 *
 * --- WHAT A RECORD IS HERE: THIRTY-TWO BYTES AND THIRTY-TWO ANSWERS -----------------------------
 *
 * bus.h answers each field of a record separately, and for a record the image does not wholly hold
 * the answers differ field by field: a field inside the image is real, a field outside READS ZERO,
 * and a write to a field outside is DROPPED — not deferred, dropped, so the next read of it is zero
 * again. `ActorRecord` is those two facts made into one object: `bytes`, the thirty-two bytes the
 * handler reads and writes, and `live`, one mask byte per record byte — $ff where the bus really
 * carries that byte and $00 where it does not.
 *
 * EVERY WRITE IS MASKED AND NO READ IS. `rec_set_b(record, off, v)` stores `v & record.live[off]`,
 * so a byte the bus drops is stored as zero and stays zero however often it is written; a read is
 * then just `record.bytes[off]`, which is the whole point — the reads are the many. A DROPPED STORE
 * IS THE CASE THAT FORCED THIS: $7378 and $73c0 do `addq.w #4,(a0) / cmp.w (a0),d0`, comparing a
 * word they just stored by RE-READING it, and test_behavior.py drives both at a record at $fffff0
 * whose x is off the image. An unmasked scratch answers the compare with the value it just wrote
 * where the original answers it with zero, and the two tests separate them.
 *
 * --- THE TWO ARMS OF THE DOOR --------------------------------------------------------------------
 *
 * FAST: the record's WB_ACTOR_RECORD_BYTES lie wholly inside the image. Then every field of it does
 * too — every offset below is under 32 and `os_in_image` has already subtracted 32 from the image's
 * top — so `bytes` is `image + address` and `live` is ACTOR_RECORD_ALL_LIVE. Nothing is copied and
 * nothing is given back: the handler writes the image where the oracle writes the image, byte for
 * byte, in the same order, and a helper entered elsewhere with the record's ADDRESS sees every write
 * as it happens.
 *
 * SLOW: it does not — the record is off the image, or it straddles the top, or its address is high
 * enough that the 24-bit bus wraps it back to the bottom mid-record (the $fffff0 case above, whose
 * last sixteen bytes fold onto $0..$f and ARE in the image while its first sixteen are not). Then
 * `bytes` is a 32-byte scratch filled through `bus_read_byte`, which carries the mask, the wrap and
 * the bound, and `live` is that same predicate per byte. Afterwards the door gives back through
 * `bus_write_byte`, which carries them again.
 *
 * THE GIVE-BACK IS THE WHOLE RECORD, and it is exact because NOTHING ELSE REACHES THE RECORD WHILE
 * THE DOOR IS OPEN. That is a property of the tier rather than of this file: every helper a body
 * calls on its OWN record takes the record — src/actor.c's damage, defeat, launch and side-flag
 * family, src/map.c's probes and settles, src/player.c's walk — and a helper that takes an ADDRESS
 * is working on a DIFFERENT record (the followed one, a shot, a spawn slot) and cannot alias this
 * one. ../STATUS.md carries the enumeration, and src/actor_view.c says what an earlier selective
 * give-back was protecting and why nothing could reach it.
 *
 * --- WHY A PER-BYTE MODEL IS EXACT AT A BOUNDARY, WHICH IS NOT OBVIOUS --------------------------
 *
 * bus.h bounds a WHOLE OPERAND: a word half in the image and half out reads 0 and is dropped, it is
 * not split. A per-byte `live` mask splits it — so the two agree only if no multi-byte access
 * straddles a boundary. The WORD accesses do not, and the reason is parity:
 *
 *   * Every word this file reads or writes on a record is at an EVEN offset — WB_ACTOR_X 0, Y 2,
 *     TYPE 4, SPRITE 6, the FLAGS/FLAGS2 PAIR read as one word at 8 (src/behavior.c's two minion
 *     and shot spawns), FIELD_12 12, HALF_WIDTH 14, SIZE_SECOND 16, FIELD_24 24, FIELD_26 26,
 *     FIELD_28 28. A byte field may sit anywhere; a byte never straddles. (The record's FIELD_22
 *     and FIELD_30 are BYTE fields, wonderboy.h; what reaches 22 four bytes wide is a `clr.l`, and
 *     that is the longword paragraph below, not this one.)
 *   * A record at `address` has at most two boundaries inside it: `OS_IMAGE_SIZE - address`, where
 *     the image's top cuts it, and `(WB_BUS_ADDR_MASK + 1) - address`, where the 24-bit bus wraps it
 *     back to zero. OS_IMAGE_SIZE and WB_BUS_ADDR_MASK + 1 are both even, so both boundaries have
 *     the parity of `address` itself.
 *   * An even-offset word straddles a boundary at offset `k` only when `k` is odd. So an EVEN record
 *     address leaves every word wholly on one side of every boundary, and the per-byte mask and the
 *     whole-operand rule give the same answer at every one of them.
 *
 * AN ODD RECORD ADDRESS IS THE CASE THE ARGUMENT DOES NOT COVER, and it is one the ORACLE cannot
 * execute: `move.w d16(a0)` with an odd a0 is an ADDRESS ERROR on a 68000, so a record base the
 * original could reach a word field through is even by construction. A differential cannot pose the
 * question.
 *
 * THE LONGWORD IS NOT LEFT TO PARITY, BECAUSE PARITY DOES NOT SAVE IT. The step above holds for a
 * word and not for a longword: a four-byte access at even offset `f` straddles a boundary at
 * `f + 2`, which is even. So `rec_l` and `rec_set_l` do not consult the mask per byte at all — they
 * ask whether all FOUR bytes are live and, when they are not, answer zero and drop the whole store,
 * which is `bus_read_long`/`bus_write_long`'s own rule rather than an approximation of it. That
 * costs one comparison against the all-live mask on the fast arm and closes the case outright; the
 * four sites it covers are offset 0 (the x/y pair copied into a spawned record), WB_ACTOR_HALF_WIDTH
 * (the respawn's `move.l #$40006,14(a0)`, whose boundary would be k = 16 — the one the suite's two
 * straddling records really sit on) and the `clr.l` pair at WB_ACTOR_FIELD_22 and WB_ACTOR_FIELD_26.
 */
#ifndef WONDERBOY_ACTOR_VIEW_H
#define WONDERBOY_ACTOR_VIEW_H

#include <stddef.h>         /* NULL — `actor_view_close` reads it as the fast arm's mark */
#include <stdint.h>

#include "bus.h"
#include "machine.h"
#include "os.h"
#include "wonderboy.h"

/* A record the door has decided about: the bytes, and which of them the bus really carries. Passed
 * BY VALUE, which is what keeps both halves in address registers for the whole of a body — a pointer
 * to it would be reloaded after every store, since a store through `uint8_t *` may alias anything.
 *
 * `bytes` is not const even in a body that only reads, because there is one type and not two; which
 * routines write is said by their names and by ../STATUS.md, not by this. */
typedef struct {
    uint8_t *bytes;
    const uint8_t *live;
} ActorRecord;

/* The mask for a record the image wholly holds: every byte real, so every write lands whole.
 * src/actor_view.c defines it, and says why the alignment is not decoration. */
extern const uint8_t ACTOR_RECORD_ALL_LIVE[WB_ACTOR_RECORD_BYTES] __attribute__((aligned(4)));

/* The door's own state: what `actor_view_close` needs to give the scratch back, and the scratch
 * itself. `image` is NULL on the fast arm and is what tells the arms apart — the record pointer
 * cannot, since on the fast arm it points INTO the image and on the slow one at a local. */
typedef struct {
    uint8_t *image;                           /* NULL on the fast arm: nothing to give back */
    uint32_t address;                         /* the record on the 24-bit bus (slow arm only) */
    uint8_t scratch[WB_ACTOR_RECORD_BYTES];   /* what the handler reads and writes */
    uint8_t live[WB_ACTOR_RECORD_BYTES];      /* $ff per byte the bus carries, $00 per byte it drops */
} ActorView;

/* The slow arm, defined in src/actor_view.c — see this file's head for why it is out of line and
 * out of this header. `actor_view_open`'s bound below is what decides which of the two runs.
 *
 * `noinline` is on the DECLARATION as well as the definition because that is where a link-time
 * optimiser would look: without it, out-of-line is only what the absence of LTO happens to give,
 * and the thing being avoided — the fill and the give-back copied into every door — is exactly what
 * LTO would do. */
__attribute__((noinline))
ActorRecord actor_view_open_scratch(ActorView *view, uint8_t *image, uint32_t address);
__attribute__((noinline))
void actor_view_close_scratch(ActorView *view);

/* THE DECISION, made once. `actor` is an address register's whole 32 bits, so it goes on the 24-bit
 * bus first for bus.h's reason — masking after a field offset was added would give the same answer
 * (the add is modulo 2^32 and the mask modulo 2^24, and every offset is far below 2^24) but
 * reasoning about that at every field is what this exists to stop doing. */
static inline ActorRecord actor_view_open(ActorView *view, uint8_t *image, uint32_t actor) {
    uint32_t address = actor & WB_BUS_ADDR_MASK;
    ActorRecord record;

    /* `os_in_image_fixed` and not `os_in_image`: the width is a literal 32, which is the case the
     * kit's collapsed form exists for — the same answer at every address, one comparison instead of
     * two, at a hundred-odd inlined doors (os.h states the equality where it defines the pair, and
     * bus.h's six accessors already spell it). */
    if (!os_in_image_fixed(address, WB_ACTOR_RECORD_BYTES))
        return actor_view_open_scratch(view, image, address);
    view->image = NULL;
    record.bytes = image + address;
    record.live = ACTOR_RECORD_ALL_LIVE;
    return record;
}

static inline void actor_view_close(ActorView *view) {
    if (view->image != NULL)
        actor_view_close_scratch(view);
}

/* THE SAME DOOR FOR A ROUTINE THAT WRITES NOTHING THROUGH THE RECORD — src/map.c's two cell probes
 * and src/actor.c's reach test, each of which publishes a `const uint8_t *image` because it writes
 * no memory at all and each of which would otherwise have to give that claim up to be opened.
 *
 * TWO THINGS MAKE IT SAFE. The const is discarded in ONE place, here, so a reader looking for the
 * discard finds it beside the rule it rests on: no `rec_set_*` may be called on the record this
 * returns. And the view is marked as having nothing to give back — `image` NULL is the fast arm's
 * mark and is set unconditionally — so a `actor_view_close` on it cannot write through the pointer
 * whose const was discarded even on the scratch arm. The compiler cannot hold a body to the first
 * rule (there is one `ActorRecord` type, not two), which is why the second exists. */
static inline ActorRecord actor_view_open_reading(ActorView *view, const uint8_t *image,
                                                  uint32_t actor) {
    ActorRecord record = actor_view_open(view, (uint8_t *)(uintptr_t)image, actor);

    view->image = NULL;
    return record;
}


/* THE OFFSET IS THE ONE ARGUMENT NOTHING BOUNDS. Most sites pass a `WB_ACTOR_*` literal, but six
 * routines take it as a runtime parameter (`bump_record_b`, `tick_countdown`,
 * `step_cursor_in_memory`, `footprint_reaches`, `type17_drift_axis`, `spend_record_b`), and the two
 * arms fail differently: on the FAST arm an offset past the record reaches the NEXT record, which is
 * wrong and which the differential says so about; on the SCRATCH arm it reaches past a 32-byte LOCAL
 * and smashes the door's own frame, which the differential cannot say anything about at all. So the
 * HOST build asserts it — a dead pytest worker where it happens, the guarded sweep's own shape — and
 * the target build does not: there is nothing on the machine to abort into, and `-nostdlib` has no
 * `__assert_fail` to call. The switch is the KIT's `-DRECREATE_HOST_DIFFERENTIAL`
 * (tools/recreate_kit/kit.mk), which is on for the candidate .so and off for every on-target build,
 * and DELIBERATELY NOT `WB_ON_TARGET`: atari/build.sh's `assert_the_sink_arm_lives_in_one_place`
 * refuses a second file carrying that arm, because the shifter sink owns it. A constant offset is
 * folded, so a wrong literal fails at the first case that reaches it. */
#ifdef RECREATE_HOST_DIFFERENTIAL
#include <assert.h>
#define REC_WITHIN_RECORD(offset, width) assert((offset) + (width) <= WB_ACTOR_RECORD_BYTES)
#else
#define REC_WITHIN_RECORD(offset, width) ((void)0)
#endif


/* --- A PROVED RECORD'S FIELDS ------------------------------------------------------------------
 *
 * bus.h's `field_b`/`field_w`/`set_field_*`/`flag_*` with the mask and the guard taken out of the
 * reads, because the door took them out once for the whole record, and with the write side reduced
 * to the mask the paragraphs above argue for. Same names in the same order, prefixed `rec_`, so that
 * a site converted from one family to the other reads the same — with ONE pair that has no `field_*`
 * counterpart to be named after: `rec_l`/`rec_set_l` mirror bus.h's `bus_read_long`/`bus_write_long`
 * at `addr_add(record, offset)`, which is what the four longword sites spell today. A site that was
 * NOT converted —
 * an access to the FOLLOWED record, to a shot, to a minion, to a band — still says
 * `field_w(image, followed, ...)` and still carries its guard.
 *
 * `rec_w` returns a SIGNED word for `field_w`'s reason: every caller doing arithmetic on a
 * coordinate wants the 68000's own sign, and a caller that wants the raw bits casts. */
static inline uint8_t rec_b(ActorRecord record, uint32_t offset) {
    REC_WITHIN_RECORD(offset, 1);
    return record.bytes[offset];
}

static inline void rec_set_b(ActorRecord record, uint32_t offset, uint8_t value) {
    REC_WITHIN_RECORD(offset, 1);
    record.bytes[offset] = (uint8_t)(value & record.live[offset]);
}

static inline int16_t rec_w(ActorRecord record, uint32_t offset) {
    REC_WITHIN_RECORD(offset, 2);
    return (int16_t)be16(record.bytes + offset);
}

static inline void rec_set_w(ActorRecord record, uint32_t offset, uint16_t value) {
    REC_WITHIN_RECORD(offset, 2);
    wr16(record.bytes + offset, (uint16_t)(value & be16(record.live + offset)));
}

/* THE TWO LONGWORD ACCESSORS ARE WHOLE-OPERAND, not per-byte: the head of this file argues that
 * parity keeps every WORD wholly inside or wholly outside the image and that a longword at an even
 * offset can straddle anyway. So these ask the mask ONE question — are all four bytes live? — and
 * answer 0 / drop the store when they are not, which is exactly `bus_read_long`/`bus_write_long`.
 * On the fast arm the question is a pointer comparison the compiler hoists out of the record. */
static inline int rec_long_is_live(ActorRecord record, uint32_t offset) {
    return record.live == ACTOR_RECORD_ALL_LIVE || be32(record.live + offset) == 0xffffffffu;
}

static inline uint32_t rec_l(ActorRecord record, uint32_t offset) {
    REC_WITHIN_RECORD(offset, 4);
    return rec_long_is_live(record, offset) ? be32(record.bytes + offset) : 0u;
}

static inline void rec_set_l(ActorRecord record, uint32_t offset, uint32_t value) {
    REC_WITHIN_RECORD(offset, 4);
    if (rec_long_is_live(record, offset))
        wr32(record.bytes + offset, value);
}

static inline int rec_flag_is_set(ActorRecord record, uint32_t offset, unsigned bit) {
    return (rec_b(record, offset) & (1u << bit)) != 0;
}

/* `bset`/`bclr`/`bchg #n,d16(An)` are BYTE read-modify-writes on memory, bus.h's note again. */
static inline void rec_flag_set(ActorRecord record, uint32_t offset, unsigned bit) {
    rec_set_b(record, offset, (uint8_t)(rec_b(record, offset) | (1u << bit)));
}

static inline void rec_flag_clear(ActorRecord record, uint32_t offset, unsigned bit) {
    rec_set_b(record, offset, (uint8_t)(rec_b(record, offset) & ~(1u << bit)));
}

static inline void rec_flag_flip(ActorRecord record, uint32_t offset, unsigned bit) {
    rec_set_b(record, offset, (uint8_t)(rec_b(record, offset) ^ (1u << bit)));
}


/* --- THE DOORS -----------------------------------------------------------------------------------
 *
 * Every routine src/behavior.c PUBLISHES is entered with a record address and nothing else — that is
 * behavior.h's interface and what test_behavior.py binds through ctypes — so each one keeps its
 * signature exactly and becomes two things: a door that opens the view, and a `static` body that
 * takes the record the door proved.
 *
 * EACH MACRO TAKES THE BODY'S ARGUMENT LIST because the bodies do not all take the same one: a body
 * whose every access is a field of its own record has no use for the image or for the address, and
 * carries neither. There are two forms and only one mechanism — the `_SIG` pair takes the door's own
 * parameter list as well, for a routine (src/map.c's probes and settles, src/player.c's walk) that
 * carries parameters of its own; the short pair below them IS that pair with the list pinned to
 * `(image, actor)`.
 *
 * THE MACROS DECLARE `view`, `record` AND `answer` IN THE DOOR'S OWN SCOPE, so a door's parameter
 * list must not use those three names — `record` in particular, since the point of the door is to
 * hand the body one. A collision is a compile error at the door and not a silent shadow, but it is
 * cheaper to know it here: name such a parameter after what it is (`followed`, `slot`, `probe`).
 *
 * A CALLER CALLS THE BODY, NEVER THE DOOR, whenever it is working on a record it already holds —
 * inside this tier or across it, src/behavior.c, src/map.c and src/player.c alike. Two doors open on
 * one record would be two SCRATCHES on the slow arm, the second filled from an image the first has
 * not given back to yet, and the outer give-back would then land on top of the inner one. */
/* THE SAME DOOR FOR A ROUTINE THAT CARRIES PARAMETERS OF ITS OWN, which is what src/map.c's probes
 * and settles and src/player.c's walk are: `params` is the door's whole parameter list and `args`
 * the body's whole argument list, each parenthesised, so a comma inside either is the list's own.
 * The door's first two parameters must still be named `image` and `actor` — that is the interface
 * test_map.py and test_player.py bind through, and it is what the view is opened on. */
#define ACTOR_DOOR_RETURNING_SIG_VIA(open, type, name, params, args)                               \
    type name params {                                                                             \
        ActorView view;                                                                            \
        ActorRecord record = open(&view, image, actor);                                            \
        type answer = name##_body args;                                                            \
                                                                                                   \
        actor_view_close(&view);                                                                   \
        return answer;                                                                             \
    }

#define ACTOR_DOOR_VOID_SIG_VIA(open, name, params, args)                                          \
    void name params {                                                                             \
        ActorView view;                                                                            \
        ActorRecord record = open(&view, image, actor);                                            \
                                                                                                   \
        name##_body args;                                                                          \
        actor_view_close(&view);                                                                   \
    }

/* The two arms above with the opener pinned: `actor_view_open` for a door whose body may WRITE the
 * record, `actor_view_open_reading` for one that may not and whose `image` is const because of it.
 * Four spellings, two mechanisms, and the open/call/close ordering written once. */
#define ACTOR_DOOR_RETURNING_SIG(type, name, params, args)                                         \
    ACTOR_DOOR_RETURNING_SIG_VIA(actor_view_open, type, name, params, args)

#define ACTOR_DOOR_VOID_SIG(name, params, args)                                                    \
    ACTOR_DOOR_VOID_SIG_VIA(actor_view_open, name, params, args)

#define ACTOR_DOOR_READING_SIG(type, name, params, args)                                           \
    ACTOR_DOOR_RETURNING_SIG_VIA(actor_view_open_reading, type, name, params, args)

#define ACTOR_DOOR_READING_VOID_SIG(name, params, args)                                            \
    ACTOR_DOOR_VOID_SIG_VIA(actor_view_open_reading, name, params, args)

/* ...and the same two with `params` pinned to `(image, actor)`, which is most doors' whole interface
 * (the head of this file counts them). Six spellings over two mechanisms, so the open/call/close
 * ordering — the answer captured BEFORE the give-back — is written once rather than six times
 * (CLAUDE.md §6). */
#define ACTOR_DOOR_RETURNING(name, ...)                                                            \
    ACTOR_DOOR_RETURNING_SIG(uint32_t, name, (uint8_t *image, uint32_t actor), (__VA_ARGS__))

#define ACTOR_DOOR_VOID(name, ...)                                                                 \
    ACTOR_DOOR_VOID_SIG(name, (uint8_t *image, uint32_t actor), (__VA_ARGS__))

#endif /* WONDERBOY_ACTOR_VIEW_H */
