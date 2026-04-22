"""Static checks for prefetch_gold.py — no network, no LLM."""
from __future__ import annotations

import ast
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prefetch_gold.py"


def test_script_parses():
    ast.parse(SCRIPT.read_text(encoding="utf-8"))


def test_script_has_main_guard():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__"' in text
    assert "def main(" in text


def test_script_skips_placeholders():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "_is_placeholder" in text
    assert "REPLACE_ME" in text
