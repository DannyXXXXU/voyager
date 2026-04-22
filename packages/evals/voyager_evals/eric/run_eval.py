"""Eric eval entry point. Placeholder — filled out in Task 1.13."""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Eric eval harness.")
    parser.add_argument("--label", default="baseline", help="Report label (baseline/p0/p1)")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls")
    args = parser.parse_args()
    print(f"[eric-eval] STUB run label={args.label} dry_run={args.dry_run}")
    print("[eric-eval] implementation lands in Task 1.13")
    return 0


if __name__ == "__main__":
    sys.exit(main())
