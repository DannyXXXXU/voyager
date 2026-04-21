"""Live smoke test: call real Copilot CLI for one transcript, print hooks.

Usage (from repo root, WSL):
    PATH=$HOME/.local/bin:$PATH uv run --package voyager-agents python scripts/smoke_copilot.py

Requires: GitHub Copilot CLI authenticated on Windows side (`copilot` + `/login`).
"""
from __future__ import annotations

import asyncio

from voyager_agents.eric.copilot_client import CopilotClaudeClient
from voyager_agents.eric.nodes_llm import HookExtraction


async def main() -> None:
    client = CopilotClaudeClient(timeout_s=120)
    transcript = (
        "Welcome to Sichuan! Today we're hiking up to 4500 meters in the "
        "Siguniang range. The air is thin, the peaks are pink at dawn, and "
        "the monks at the base monastery serve yak butter tea so thick you "
        "could stand a spoon in it. If you thought Switzerland was dramatic, "
        "wait until you see this valley."
    )
    result = await client.complete(
        system=(
            "You extract short attention-grabbing hooks (1-2 sentences each) "
            "from a video transcript. Return strict JSON matching the HookExtraction schema."
        ),
        user=f"VIDEO_ID=smoke-001\nTRANSCRIPT:\n{transcript}",
        schema=HookExtraction,
    )
    print("=== HookExtraction ===")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
