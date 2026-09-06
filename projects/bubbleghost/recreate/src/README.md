Each reconstructed subsystem lives here as `src/<subsystem>.c` — the readable C core plus its
`g_<name>` glue — with its addresses and prototypes in `include/<subsystem>.h` and its differential
battery in `test/test_<subsystem>.py`. See [`../README.md`](../README.md), "Adding a function".
