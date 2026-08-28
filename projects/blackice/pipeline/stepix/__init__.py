"""stepix -- asset pipeline for a Wolfenstein-style Atari STE raycaster.

Every module converts host-side art (PNG / numpy) into a format the 68000 engine reads
directly. The byte-exact contract for each format is in README.md, which is the document the
C engine is written against; these modules are its reference implementation.
"""
