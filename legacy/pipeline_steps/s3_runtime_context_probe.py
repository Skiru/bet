#!/usr/bin/env python3
"""C7 safe runtime probe: confirms a second child inherits the same context."""

from __future__ import annotations

import os

from bet.pipeline.runtime_execution import (
    RuntimeDatabaseAccessPolicy,
    RuntimeDbRole,
    RuntimeExecutionContext,
)


def main() -> None:
    context = RuntimeExecutionContext.from_child_env(dict(os.environ))
    context.verify_filesystem_bindings()
    conn = RuntimeDatabaseAccessPolicy(context).connect(RuntimeDbRole.SHADOW_READ_WRITE)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM runtime_context_probe WHERE stage = 'S2'"
        ).fetchone()[0]
        if count != 1:
            raise RuntimeError("RUNTIME_CONTEXT_PROBE_PREDECESSOR_MISSING")
        conn.execute(
            "INSERT OR REPLACE INTO runtime_context_probe(stage) VALUES ('S3')"
        )
        conn.commit()
    finally:
        conn.close()
    print("RUNTIME_CONTEXT_PROBE=S3")


if __name__ == "__main__":
    main()
