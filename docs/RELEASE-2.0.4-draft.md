# Toolkit 2.0.4 (draft): point fixes

- **A stale checkpoint no longer pastes an old recipe** (A2, the second lead run): a build that
  starts after the layout steps (`--from diff` on the host) took `out/<step>/` as it stood even
  when the source had changed since, so write_layout wrote (and the paste laid) the old recipe.
  Each layout step now records the source it was laid from (`out/<step>/source.json`); a stale
  checkpoint (including an older toolkit's, which has no stamp) is laid out again, every step and
  checkpoint. `fk look` judges the new `.fkp` against the old game as DRIFT, and notes a placed
  module's `.fk` change not built yet.
