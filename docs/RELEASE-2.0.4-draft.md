# Toolkit 2.0.4 (draft): point fixes

- **A stale checkpoint no longer pastes an old recipe** (A2, the second lead run): a build that
  starts after the layout steps (`--from diff` on the host) took `out/<step>/` as it stood even
  when the source had changed since, so write_layout wrote (and the paste laid) the old recipe.
  Each checkpoint now records the source it was laid from (`out/<step>/source.json`), and a stale
  one is laid out again; `fk look`, which judges against the `.fkp` files, adds a note when a
  placed module's `.fk` changed since its `.fkp` was written.
