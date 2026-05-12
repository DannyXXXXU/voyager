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

import json_repair

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


def _parse_json_with_repair(body: str) -> tuple[Any, str | None]:
    """Try strict json.loads; on failure, fall back to json_repair.loads.

    Returns (parsed, repair_note). repair_note is None on strict success,
    or a short message describing the repair attempt outcome.
    Raises json.JSONDecodeError if both strict and repair fail to produce
    a non-None object.
    """
    try:
        return json.loads(body), None
    except json.JSONDecodeError as strict_err:
        try:
            repaired = json_repair.loads(body)
        except Exception as e:  # noqa: BLE001 - json_repair raises various
            raise strict_err from e
        if repaired is None or repaired == "":
            # json_repair returns "" on total failure rather than raising.
            raise strict_err
        return repaired, f"repaired ({type(strict_err).__name__}: {strict_err.msg})"



def _ts_type(annotation: Any) -> str:
    """Render a python typing annotation as a TypeScript-ish type string."""
    import typing as _t
    origin = _t.get_origin(annotation)
    args = _t.get_args(annotation)
    # Union / Optional
    if origin in (_t.Union,) or str(origin) == "types.UnionType":
        non_none = [a for a in args if a is not type(None)]
        rendered = " | ".join(_ts_type(a) for a in non_none)
        if len(non_none) < len(args):
            rendered += " | null"
        return rendered
    # list / List
    if origin in (list, _t.List):  # noqa: UP006
        inner = _ts_type(args[0]) if args else "any"
        return f"Array<{inner}>"
    # dict / Dict
    if origin in (dict, _t.Dict):  # noqa: UP006
        k = _ts_type(args[0]) if args else "string"
        v = _ts_type(args[1]) if len(args) > 1 else "any"
        return f"Record<{k}, {v}>"
    # Nested pydantic BaseModel — render inline
    try:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return _pydantic_to_ts_body(annotation)
    except TypeError:
        pass
    # Primitives
    if annotation is str:
        return "string"
    if annotation in (int, float):
        return "number"
    if annotation is bool:
        return "boolean"
    if annotation is type(None):
        return "null"
    # Fallback: use the name if available.
    return getattr(annotation, "__name__", "any")


def _pydantic_to_ts_body(schema: type[BaseModel]) -> str:
    """Render a pydantic model as an inline TS-style object literal."""
    lines = ["{"]
    for name, field in schema.model_fields.items():
        ts = _ts_type(field.annotation)
        comment = f"  // {field.description}" if field.description else ""
        lines.append(f"  {name}: {ts};{comment}")
    lines.append("}")
    return "\n".join(lines)


def pydantic_to_ts_interface(schema: type[BaseModel]) -> str:
    """Render `interface <Name> { ... }` for the schema and any nested models."""
    body = _pydantic_to_ts_body(schema)
    return f"interface {schema.__name__} {body}"


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
        max_retries: int = 3,
        backoff_base_s: float = 2.0,
        log_dir: Path | str | None = None,
    ) -> None:
        self._model = model
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._log_dir: Path | None = Path(log_dir) if log_dir else None
        if self._log_dir is not None:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        _STAGE_WSL.mkdir(parents=True, exist_ok=True)
        if not _PS1_WSL.exists():
            raise CopilotCLIError(f"run_copilot.ps1 not found at {_PS1_WSL}")

    async def complete(
        self,
        system: str,
        user: str,
        schema: type[BaseModel] | None = None,
        log_tag: str | None = None,
    ) -> BaseModel | str:
        prompt = self._build_prompt(system, user, schema)
        last_err: Exception | None = None

        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                # Exponential backoff between retries: 2s, 4s, 8s ...
                delay = self._backoff_base_s * (2 ** (attempt - 1))
                await asyncio.sleep(delay)
            try:
                raw = await self._invoke(prompt)
            except CopilotCLIError as e:
                # Network / CLI failure — also worth retrying with backoff.
                last_err = e
                self._dump_log(log_tag, attempt, prompt, raw=None, error=str(e))
                continue
            self._dump_log(log_tag, attempt, prompt, raw=raw, error=None)
            if schema is None:
                return raw
            body = _extract_json_text(raw)
            try:
                data, repair_note = _parse_json_with_repair(body)
                return schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_err = e
                # Corrective retry — feed the error back so the model can fix it.
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
    def _dump_log(
        self,
        log_tag: str | None,
        attempt: int,
        prompt: str,
        raw: str | None,
        error: str | None,
    ) -> None:
        """Persist prompt + raw stdout (or error) to log_dir for post-hoc debugging."""
        if self._log_dir is None or log_tag is None:
            return
        try:
            path = self._log_dir / f"{log_tag}_{attempt:02d}.txt"
            parts = [
                f"=== TAG: {log_tag}  ATTEMPT: {attempt}  MODEL: {self._model} ===",
                "--- PROMPT ---",
                prompt,
                "--- RAW STDOUT ---",
                raw if raw is not None else "(no stdout — invocation error)",
            ]
            if error:
                parts += ["--- ERROR ---", error]
            path.write_text("\n".join(parts), encoding="utf-8")
        except Exception:  # noqa: BLE001 — logging must never break a run
            pass
    def _build_prompt(
        self, system: str, user: str, schema: type[BaseModel] | None
    ) -> str:
        parts = [f"SYSTEM:\n{system}", f"USER:\n{user}"]
        if schema is not None:
            parts.append(
                "RESPONSE FORMAT:\n"
                "Return ONLY a raw JSON object — no prose, no markdown fences, "
                "no explanations. The JSON must match this TypeScript interface "
                "(field types are exact; comments describe constraints):\n"
                f"{pydantic_to_ts_interface(schema)}"
            )
            # Determinism hint + brace prefill — keeps the model anchored on
            # the JSON-only contract and reduces stochastic preamble drift.
            parts.append(
                "DETERMINISM:\n"
                "Be deterministic. Identical inputs MUST produce identical output. "
                "Prefer literal phrasings already present in the transcript. "
                "Do not invent facts, dates, or place names not in the source. "
                "Do not add filler, hedging, or commentary."
            )
            parts.append(
                "BEGIN YOUR RESPONSE WITH THE CHARACTER `{` AND END WITH `}`. "
                "Output NOTHING before the opening brace and NOTHING after the "
                "closing brace — no markdown fences, no prose, no explanation."
            )
        else:
            # For free-form (e.g. brief) outputs we still want determinism.
            parts.append(
                "DETERMINISM:\n"
                "Be deterministic. Identical inputs MUST produce identical output. "
                "Do not invent facts not present in the inputs. No filler."
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
