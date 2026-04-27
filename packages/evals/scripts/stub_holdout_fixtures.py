"""Task 1.19e — generate empty stub fixture YAMLs for the 5 holdout videos.

Holdout fixtures must NEVER be agent-drafted; they exist precisely to test
generalization on data the model has not seen during iteration. This script
creates a skeleton YAML per holdout entry in seed.yaml so Danny can fill in
gold_hooks / gold_selling_points by hand from the prefetched transcripts.

Output: packages/evals/voyager_evals/eric/fixtures/<id>.yaml
        packages/evals/voyager_evals/eric/fixtures/<id>.transcript.txt
        (transcript copied from gold/ for easy reference while labeling)

Idempotent: skips files that already exist unless --force.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
ERIC_DIR = REPO_ROOT / "packages" / "evals" / "voyager_evals" / "eric"
GOLD_DIR = ERIC_DIR / "gold"
SEED_PATH = ERIC_DIR / "seed.yaml"
FIXTURES_DIR = ERIC_DIR / "fixtures"


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    seed = yaml.safe_load(SEED_PATH.read_text(encoding="utf-8"))
    holdout = seed.get("holdout", [])
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    for entry in holdout:
        fid = entry["id"]
        out_yaml = FIXTURES_DIR / f"{fid}.yaml"
        out_txt = FIXTURES_DIR / f"{fid}.transcript.txt"

        if out_yaml.exists() and not args.force:
            print(f"[skip] {fid} (exists)")
            skipped += 1
            continue

        # Read transcript for sha + side-by-side reference file
        tr_path = GOLD_DIR / "transcripts" / f"{entry['video_id']}.json"
        if not tr_path.exists():
            print(f"[!]  {fid}: missing gold transcript {tr_path}")
            continue
        tr = json.loads(tr_path.read_text(encoding="utf-8"))
        text = tr.get("text", "")
        sha = _sha256(text)

        stub = {
            "id": fid,
            "video_id": entry["video_id"],
            "topic": entry["topic"],
            "difficulty": entry["difficulty"],
            "content_type": entry["content_type"],
            "holdout": True,
            "gold_hooks": [
                # Example shape — DELETE these placeholders and add real ones:
                # - text: "the exact hook line from transcript"
                #   aliases: ["paraphrase 1", "paraphrase 2"]
                #   timestamp_s: 12.5
            ],
            "gold_selling_points": [
                # - text: "abstract benefit / reason to watch"
                #   aliases: ["paraphrase 1"]
            ],
            "notes": entry.get("notes", ""),
            "transcript_sha256": sha,
            "_meta": {
                "drafted_by": "human",
                "drafted_at_utc": None,
                "review_status": "stub",  # stub → in_progress → approved
                "labeler": None,
            },
        }
        out_yaml.write_text(
            yaml.safe_dump(stub, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        out_txt.write_text(text, encoding="utf-8")
        print(f"[stub] {fid}  → {out_yaml.name} (+ {out_txt.name})")
        written += 1

    # Update _draft_report.json with holdout stub timestamp
    print(f"\nStubs written: {written} | Skipped: {skipped}")
    print(f"Now hand-label them; see {ERIC_DIR / 'fixtures' / 'REVIEW.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
