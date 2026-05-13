"""Recover hooks aliases from Copilot CLI raw stdout logs (no LLM re-run).

Reads each reports/_alias_logs/alias-dev-*-hooks_00.txt, extracts the JSON
between '--- RAW STDOUT ---' and EOF (stripping markdown fences), parses to
AliasBatch, and writes aliases back into fixtures/<id>.yaml gold_hooks[].

Selling-points aliases were never generated (script crashed before sp loop);
those need a separate run with the fixed gen_aliases.py.

Usage:
  uv run --project packages/evals python scripts/recover_aliases_from_logs.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml
from json_repair import repair_json

ROOT = Path.home() / "projects/voyager"
LOG_DIR = ROOT / "packages/evals/voyager_evals/eric/reports/_alias_logs"
FIX_DIR = ROOT / "packages/evals/voyager_evals/eric/fixtures"


def extract_json(raw: str) -> dict:
    # Pull text between '--- RAW STDOUT ---' and end (or next '---' divider)
    m = re.search(r"--- RAW STDOUT ---\n(.*?)(?:\n--- |\Z)", raw, re.DOTALL)
    if not m:
        raise ValueError("no RAW STDOUT section")
    text = m.group(1).strip()
    # strip ```json fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(repair_json(text))


def main() -> None:
    results = []
    for log in sorted(LOG_DIR.glob("alias-dev-*-hooks_00.txt")):
        fid = log.stem.replace("alias-", "").replace("-hooks_00", "")
        fix_fp = FIX_DIR / f"{fid}.yaml"
        if not fix_fp.exists():
            results.append({"fixture": fid, "error": "yaml missing"}); continue
        try:
            payload = extract_json(log.read_text(encoding="utf-8"))
        except Exception as e:
            results.append({"fixture": fid, "error": f"parse: {e}"}); continue

        data = yaml.safe_load(fix_fp.read_text())
        hooks = data.get("gold_hooks") or []
        by_idx = {item["index"]: item["aliases"] for item in payload.get("items", [])}
        filled = 0
        for i, h in enumerate(hooks):
            if h.get("aliases"):
                continue
            al = by_idx.get(i)
            if not al:
                continue
            h["aliases"] = al
            filled += 1
        if filled:
            fix_fp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        results.append({"fixture": fid, "hooks_filled": filled, "total_hooks": len(hooks)})

    out = LOG_DIR / "recovery_summary.json"
    out.write_text(json.dumps(results, indent=2))
    for r in results:
        print(r)
    total = sum(r.get("hooks_filled", 0) for r in results)
    print(f"\n[recover] total hooks aliases filled: {total}")
    print(f"[recover] summary → {out}")


if __name__ == "__main__":
    main()
