"""Minimal adapter: reuse the existing upstream browser-use executor.

Replace the body with your own agent. Return ExecutionResult, never judge here.
The framework owns one process per task. No reference answer is supplied.
"""

import os

from browser_use.llm import ChatOpenAI

from frameworks import ExecutionResult
from frameworks.browser_use.run_task import execute as upstream_execute


async def execute(instruction: str) -> ExecutionResult:
    model = ChatOpenAI(
        model=os.environ.get("MY_AGENT_MODEL", "gpt-4.1-mini"),
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL"),
    )
    return await upstream_execute(instruction, llm=model, browser_name="local_headless")
