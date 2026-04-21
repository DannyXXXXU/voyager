"""Real Copilot CLI client — shells out to GitHub Copilot CLI on Windows from WSL.

Invocation path (WSL -> Windows):
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File <ps1> -PromptFile <win_path>

The PowerShell wrapper exists because direct `cmd.exe /c "copilot.cmd -p \"...\""`
fails with "too many arguments" whenever the prompt contains embedded quotes —
cmd.exe's quote handling mangles them. PowerShell + `Get-Content -Raw` sidesteps
the shell-escape problem entirely by passing the prompt as a PS string variable.

The CLI output typically looks like:
    ```json
    {"hooks": [...]}
    ```


    Changes   +0 -0
    Requests  3 Premium (9s)
    Tokens    ↑ 23k • ↓ 20

We strip the trailing stats block and any markdown fences, then json.loads.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PS1_WSL = _REPO_ROOT / "scripts" / "win" / "run_copilot.ps1"

# Prompt staging directory — must be readable from Windows side.
# /mnt/c/temp/voyager/ => C:\temp\voyager\ on Windows.
_STAGE_WSL = Path("/mnt/c/temp/voyager/copilot_runs")


def _wsl_to_windows(p: Path) -> str:
    """Convert /mnt/c/foo/bar to C:\\foo\\bar."""
    s = str(p)
    if s.startswith("/mnt/"):
        drive = s[5]
        rest = s[7:].replace("/", "\\")
        return f"{drive.upper()}:\\{rest}"
    # Fall back to wslpath if available.
    wp = shutil.which("wslpath")
    if wp:
        import subprocess

        return subprocess.check_output([wp, "-w", str(p)], text=True).strip()
    raise RuntimeError(f"Cannot convert WSL path to Windows path: {p}")


# --------------------------------------------------------------------------- #
# Output parsing
# --------------------------------------------------------------------------- #
_STATS_LINE = re.compile(r"^\s*(Changes|Requests|Tokens)\s", re.MULTILINE)
_FENCE = re.compile(r"^```(?:json)?\s*\n?|\n?```\s*$", re.MULTILINE)


def _extract_json_text(raw: str) -> str:
    """Strip Copilot CLI trailer (Changes/Requests/Tokens) and markdown fences."""
    # Cut at the first stats line, if present.
    m = _STATS_LINE.search(raw)
    body = raw[: m.start()] if m else raw
    body = body.strip()
    # Remove triple-backtick fences (```json ... ``` or ``` ... ```).
    body = _FENCE.sub("", body).strip()
    # If the model wrapped extra prose, grab the first {...} or [...] block.
    if not (body.startswith("{") or body.startswith("[")):
        brace = body.find("{")
        bracket = body.find("[")
        starts = [i for i in (brace, bracket) if i >= 0]
        if starts:
            start = min(starts)
            body = body[start:]
    return body


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class CopilotCLIError(RuntimeError):
    """Raised when the Copilot CLI invocation fails or returns unparseable output."""


class CopilotClaudeClient:
    """Shells out to the Copilot CLI running under Windows PowerShell.

    Parameters
    ----------
    model: CLI model id (default "claude-sonnet-4.5").
    timeout_s: per-call wallclock cap.
    max_retries: on JSON parse / schema validation failure, retry with a
        corrective suffix added to the user prompt.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4.5",
        timeout_s: int = 180,
        max_retries: int = 1,
    ) -> None:
        self._model = model
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        _STAGE_WSL.mkdir(parents=True, exist_ok=True)
        if not _PS1_WSL.exists():
            raise CopilotCLIError(f"run_copilot.ps1 not found at {_PS1_WSL}")

    async def complete(
        self,
        system: str,
        user: str,
        schema: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        prompt = self._build_prompt(system, user, schema)
        last_err: Exception | None = None

        for attempt in range(self._max_retries + 1):
            raw = await self._invoke(prompt)
            if schema is None:
                return raw
            body = _extract_json_text(raw)
            try:
                data = json.loads(body)
                return schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_err = e
                # Corrective retry.
                prompt = (
                    self._build_prompt(system, user, schema)
                    + "\n\nPREVIOUS ATTEMPT WAS INVALID. "
                    f"Error: {type(e).__name__}: {e}. "
                    "Return ONLY a raw JSON object matching the schema. No prose, no markdown fences."
                )
        raise CopilotCLIError(
            f"Copilot CLI produced unparseable output after {self._max_retries + 1} attempts: {last_err}"
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _build_prompt(
        self, system: str, user: str, schema: type[BaseModel] | None
    ) -> str:
        parts = [f"SYSTEM:\n{system}", f"USER:\n{user}"]
        if schema is not None:
            parts.append(
                "RESPONSE FORMAT:\n"
                "Return ONLY a raw JSON object — no prose, no markdown fences, "
                "no explanations. The JSON must validate against this schema:\n"
                f"{json.dumps(schema.model_json_schema(), indent=2)}"
            )
        return "\n\n".join(parts)

    async def _invoke(self, prompt: str) -> str:
        # Stage the prompt as a file readable from Windows.
        rid = uuid.uuid4().hex[:12]
        prompt_path = _STAGE_WSL / f"{rid}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        try:
            ps1_win = _wsl_to_windows(_PS1_WSL)
            prompt_win = _wsl_to_windows(prompt_path)
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps1_win,
                "-PromptFile",
                prompt_win,
                "-Model",
                self._model,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout_s
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise CopilotCLIError(
                    f"Copilot CLI timed out after {self._timeout_s}s"
                )
            if proc.returncode != 0:
                raise CopilotCLIError(
                    f"Copilot CLI exited {proc.returncode}: "
                    f"{stderr_b.decode('utf-8', errors='replace')[:500]}"
                )
            return stdout_b.decode("utf-8", errors="replace")
        finally:
            if os.environ.get("VOYAGER_KEEP_PROMPTS") != "1":
                try:
                    prompt_path.unlink()
                except FileNotFoundError:
                    pass


__all__ = ["CopilotClaudeClient", "CopilotCLIError"]
