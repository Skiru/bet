"""Run lightweight pipeline unit tests directly.

This script imports the test helpers and runs the test functions directly.
It's intended for quick local verification without invoking the full pytest run.
"""
from __future__ import annotations

from bet.pipeline.tests.test_pipeline_unit import (
    test_pipeline_stage_flow,
    test_run_single_day_pipeline_smoke,
)


def main():
    test_pipeline_stage_flow()
    test_run_single_day_pipeline_smoke()
    print("OK")


if __name__ == "__main__":
    main()
