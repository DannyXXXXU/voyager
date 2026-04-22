"""Prefetch Eric eval gold data — transcripts + top comments — once.

Usage (from repo root, in WSL):

    ~/.local/bin/uv run --package voyager-evals \
        python packages/evals/scripts/prefetch_gold.py \
        --seed packages/evals/voyager_evals/eric/seed.yaml \
        --gold-dir packages/evals/voyager_evals/eric/gold \
        --only dev                     # or: holdout, or omit for both
        --skip-existing

What it does, per seed entry whose video_id is NOT "REPLACE_ME_*":
    1. download audio via voyager_tools.audio_download (backend=apify if
       APIFY_TOKEN env set, else yt-dlp fallback)
    2. transcribe via voyager_tools.whisper_client → save gold/transcripts/<vid>.json
    3. fetch top 50 comments via voyager_tools.comments_fetch → save gold/comments/<vid>.json

Budget safety:
    - With Whisper at ~$0.006/min, 20 videos × ~15min avg ≈ $1.80.
    - YouTube Data API comments_fetch is free within daily quota.
    - Audio download via Apify: ~$0.05/video → ~$1. Total one-shot ≈ $3.

Re-run safety:
    --skip-existing skips any video that already has BOTH gold files.
    Idempotent.

IDs in seed.yaml starting with "REPLACE_ME_" are SKIPPED with a warning —
fill them in before re-running.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

import yaml

logger = logging.getLogger("prefetch_gold")


def _is_placeholder(video_id: str) -> bool:
    return video_id.startswith("REPLACE_ME") or video_id.strip() == ""


def _save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, default=str, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _prefetch_one(
    video_id: str,
    gold_dir: Path,
    audio_out: Path,
    apify_token: str | None,
    skip_existing: bool,
) -> dict:
    """Returns a status dict for the report."""
    # Deferred imports so --help works even if voyager_tools not yet built.
    from voyager_tools import audio_download, comments_fetch, whisper_client
    from voyager_tools.errors import (
        AudioTooLargeError,
        AuthRequiredError,
        QuotaExceededError,
        VideoUnavailableError,
    )

    tr_path = gold_dir / "transcripts" / f"{video_id}.json"
    cm_path = gold_dir / "comments" / f"{video_id}.json"
    if skip_existing and tr_path.exists() and cm_path.exists():
        return {"video_id": video_id, "status": "skipped_existing"}

    result = {"video_id": video_id, "status": "ok", "errors": []}

    # 1. audio + 2. transcribe ------------------------------------------------
    if not tr_path.exists():
        try:
            backend = "apify" if apify_token else "ytdlp"
            audio = audio_download.download_audio(
                video_id=video_id,
                output_dir=audio_out,
                backend=backend,
                token=apify_token,
            )
        except (VideoUnavailableError, AuthRequiredError) as exc:
            return {"video_id": video_id, "status": "audio_unavailable", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"video_id": video_id, "status": "audio_failed", "error": str(exc)}

        try:
            tr = await whisper_client.transcribe(audio_path=audio.path)
        except AudioTooLargeError as exc:
            return {"video_id": video_id, "status": "audio_too_large", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"video_id": video_id, "status": "transcribe_failed", "error": str(exc)}

        _save_json(
            tr_path,
            {
                "text": tr.text,
                "language": tr.language,
                "duration_s": tr.duration_s,
                "segments": tr.segments or [],
            },
        )

    # 3. comments -------------------------------------------------------------
    if not cm_path.exists():
        try:
            comments = comments_fetch.fetch_top_comments(
                video_id=video_id, max_comments=50
            )
        except QuotaExceededError as exc:
            return {"video_id": video_id, "status": "comments_quota", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"video_id": video_id, "status": "comments_failed", "error": str(exc)}

        _save_json(
            cm_path,
            [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in comments],
        )

    return result


async def _main_async(args: argparse.Namespace) -> int:
    import os

    seed = yaml.safe_load(Path(args.seed).read_text(encoding="utf-8"))
    gold_dir = Path(args.gold_dir)
    audio_out = Path(args.audio_dir or tempfile.gettempdir()) / "voyager_gold_audio"
    audio_out.mkdir(parents=True, exist_ok=True)

    buckets = []
    if args.only in (None, "dev"):
        buckets.append(("dev", seed.get("dev", [])))
    if args.only in (None, "holdout"):
        buckets.append(("holdout", seed.get("holdout", [])))

    apify_token = os.environ.get("APIFY_TOKEN")
    if not apify_token:
        logger.warning("APIFY_TOKEN not set — falling back to yt-dlp (may fail on cloud IPs)")

    report = []
    for bucket_name, entries in buckets:
        for entry in entries:
            vid = entry["video_id"]
            if _is_placeholder(vid):
                logger.warning("skip placeholder %s/%s", bucket_name, entry["id"])
                report.append(
                    {"video_id": vid, "fixture_id": entry["id"], "status": "placeholder"}
                )
                continue
            logger.info("prefetch %s/%s video_id=%s", bucket_name, entry["id"], vid)
            res = await _prefetch_one(
                video_id=vid,
                gold_dir=gold_dir,
                audio_out=audio_out,
                apify_token=apify_token,
                skip_existing=args.skip_existing,
            )
            res["fixture_id"] = entry["id"]
            res["bucket"] = bucket_name
            report.append(res)

    # Print one-line summary per entry, JSON report at end.
    for r in report:
        logger.info("  %-20s %-18s %s", r.get("fixture_id"), r["status"], r["video_id"])

    report_path = gold_dir / "_prefetch_report.json"
    _save_json(report_path, report)
    logger.info("wrote report → %s", report_path)

    failures = [r for r in report if r["status"] not in ("ok", "skipped_existing", "placeholder")]
    return 1 if failures else 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", required=True)
    p.add_argument("--gold-dir", required=True)
    p.add_argument("--only", choices=["dev", "holdout"], default=None)
    p.add_argument("--audio-dir", default=None, help="defaults to tempdir")
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )

    sys.exit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
