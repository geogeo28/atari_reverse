/* entry_probe.c — the one function `rom_bench.py` links into every ROM-BENCH blob.
 *
 * Its whole body is the `rts`, and that is what it is for: `RomBench._measure_overhead` runs it
 * through BOTH of the oracle's entry points and takes what is left after a 68000's 16-cycle `rts`
 * as the ENTRY OVERHEAD — the instruction and the reset cycles Musashi charges before either door
 * executes anything of the function under test. Every Tier 3 ratio is computed net of it, so it is
 * measured on a function with nothing in it rather than written down as a number that could drift
 * the day the oracle's reset does.
 *
 * It is compiled with the PROJECT's own target flags, exactly as the cores beside it are, so the
 * measurement also proves that the cross build produced a blob the oracle can stage and call at all
 * — which is the first thing to go wrong and the last thing a cycle count would say.
 *
 * KIT-SIDE, and the name is `rom_bench`'s: a project has no reason to write this file, and two
 * projects writing it would be two constants with one meaning.
 */

void rom_bench_entry_probe(void);

void rom_bench_entry_probe(void)
{
}
