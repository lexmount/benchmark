"""Synthetic adapter used only by test_bu_v1_1; never a benchmark result."""

import os

from lexmount_v1_1.executors import MeasuredExecutionResult


async def execute(instruction):
    if not isinstance(instruction, str):
        raise TypeError("Solver input is instruction only")
    return MeasuredExecutionResult(
        final_result="Synthetic fixture only",
        steps=["Synthetic fixture"],
        screenshots_b64=[],
        num_steps=0,
        duration_seconds=0,
        cost=None,
        metrics={"fixture_pid": os.getpid()},
    )
