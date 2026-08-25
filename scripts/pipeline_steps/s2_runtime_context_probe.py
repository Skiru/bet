#!/usr/bin/env python3
"""C7 safe runtime probe: validates inherited context and writes only shadow DB."""

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
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runtime_context_probe (stage TEXT PRIMARY KEY)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO runtime_context_probe(stage) VALUES ('S2')"
        )
        conn.commit()
    finally:
        conn.close()
    print("RUNTIME_CONTEXT_PROBE=S2")


if __name__ == "__main__":
    main()
