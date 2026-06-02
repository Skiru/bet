Archived scripts snapshot (2026-06-02)

This folder contains scripts moved out of `scripts/` during the 2026-06-02 cleanup.

Reason: these are small, ad-hoc maintenance or live-test utilities that are not
referenced by the main pipeline steps and clutter the top-level `scripts/`
namespace. They are preserved here for history and manual reuse.

Files:
- check_team_garbage.py — maintenance tool for detecting team-name duplicates and data splits
- test_bovada_feed.py — ad-hoc Bovada public feed probe

If you want one of these restored to `scripts/`, move it back and update any
invocation docs that reference it.
