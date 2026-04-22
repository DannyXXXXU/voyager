"""Search YouTube for Eric eval fixture candidates.

Usage (in WSL, repo root):

    export YOUTUBE_API_KEY=$(cmd.exe /c 'az keyvault secret show \\
        --vault-name kv-voyager-sexwh5 --name youtube-api-key \\
        --query value -o tsv')
    ~/.local/bin/uv run --package voyager-evals python \\
        packages/evals/scripts/search_candidates.py \\
        --out packages/evals/voyager_evals/eric/candidates.yaml

Strategy:
    For each (content_type, difficulty, query) triple below, hits YouTube
    Data API and keeps the top-3 results. Outputs a reviewable YAML listing
    title / channel / video_id / duration_estimate so Danny can pick 20 from
    the candidate pool and paste them back into seed.yaml.

Budget: ~20 search.list calls × 100 quota units = 2000 units. Free tier is
10K/day, so ~5 runs/day is safe.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

# Curated query plan — aims for English overseas-creator POV of mainland China.
# Keep queries short; YouTube search relevance is better with terse phrases.
QUERY_PLAN: list[dict] = [
    # -------- easy (clear single-topic, ~5-10min) --------
    {"content_type": "food", "difficulty": "easy", "query": "chengdu street food hot pot"},
    {"content_type": "food", "difficulty": "easy", "query": "xi'an breakfast market tour"},
    {"content_type": "vlog", "difficulty": "easy", "query": "first day in shanghai"},
    {"content_type": "travel", "difficulty": "easy", "query": "china high speed rail experience"},
    {"content_type": "culture", "difficulty": "easy", "query": "hanfu forbidden city beijing"},
    # -------- medium (mixed topics, 10-20min) --------
    {"content_type": "food", "difficulty": "medium", "query": "yunnan mushroom hot pot"},
    {"content_type": "vlog", "difficulty": "medium", "query": "shenzhen huaqiangbei electronics"},
    {"content_type": "travel", "difficulty": "medium", "query": "zhangjiajie avatar mountain trip"},
    {"content_type": "culture", "difficulty": "medium", "query": "chengdu tea house mahjong"},
    {"content_type": "nature", "difficulty": "medium", "query": "jiuzhaigou autumn waterfalls"},
    # -------- hard (long-form, abstract, 20-40min) --------
    {"content_type": "vlog", "difficulty": "hard", "query": "xinjiang road trip urumqi kashgar"},
    {"content_type": "history", "difficulty": "hard", "query": "great wall mutianyu history"},
    {"content_type": "travel", "difficulty": "hard", "query": "harbin ice festival winter"},
    {"content_type": "culture", "difficulty": "hard", "query": "guangzhou dim sum cantonese"},
    {"content_type": "food", "difficulty": "hard", "query": "sichuan spicy food tour"},
    # -------- extras / holdout candidates --------
    {"content_type": "vlog", "difficulty": "easy", "query": "americans try china food"},
    {"content_type": "travel", "difficulty": "medium", "query": "pingyao ancient town"},
    {"content_type": "culture", "difficulty": "hard", "query": "chinese opera backstage"},
    {"content_type": "history", "difficulty": "hard", "query": "terracotta warriors xian documentary"},
    {"content_type": "nature", "difficulty": "medium", "query": "guilin li river cruise"},
]


def _call_youtube(query: str, max_results: int, api_key: str) -> list[dict]:
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    resp = yt.search().list(
        q=query,
        type="video",
        part="snippet",
        maxResults=max_results,
        regionCode="US",
        relevanceLanguage="en",
        videoDuration="medium",  # 4-20 min — filters out shorts + long vlogs
        safeSearch="moderate",
    ).execute()
    out = []
    for item in resp.get("items", []):
        out.append(
            {
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channel_title": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
                "description_snippet": item["snippet"].get("description", "")[:200],
            }
        )
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--per-query", type=int, default=3)
    args = p.parse_args()

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("ERROR: YOUTUBE_API_KEY not set", file=sys.stderr)
        return 2

    results: list[dict] = []
    for plan in QUERY_PLAN:
        print(f"[{plan['content_type']}/{plan['difficulty']}] {plan['query']}", file=sys.stderr)
        try:
            hits = _call_youtube(plan["query"], args.per_query, api_key)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}", file=sys.stderr)
            continue
        for h in hits:
            h["content_type"] = plan["content_type"]
            h["difficulty"] = plan["difficulty"]
            h["query"] = plan["query"]
        results.extend(hits)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(results, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"wrote {len(results)} candidates → {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
