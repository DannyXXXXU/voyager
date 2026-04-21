"""Dev smoke — NOT a unit test.

Runs the Eric data subgraph end-to-end against live Azure + YouTube + Postgres,
using Key Vault `kv-voyager-sexwh5` for secrets. Success criterion: at least 1
Video row, 1 Transcript row, and 1+ Comment rows persisted, with
llm_status=pending on the video.

Usage:
    export PATH=$HOME/.local/bin:$PATH
    az login
    uv run --package voyager-agents python scripts/smoke_local.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback

from sqlalchemy import create_engine, text
from sqlmodel import Session

from voyager_agents.eric.graph import build_data_graph
from voyager_agents.eric.state import EricState
from voyager_common import load_from_keyvault

KEY_VAULT_NAME = os.environ.get("KEY_VAULT_NAME", "kv-voyager-sexwh5")
TOPIC = os.environ.get("SMOKE_TOPIC", "west sichuan travel")
MAX_VIDEOS = int(os.environ.get("SMOKE_MAX_VIDEOS", "2"))


def main() -> int:
    print(f"→ loading secrets from Key Vault {KEY_VAULT_NAME}…")
    settings = load_from_keyvault(KEY_VAULT_NAME)
    for f in (
        "database_url",
        "azure_openai_endpoint",
        "azure_openai_key",
        "youtube_api_key",
        "apify_token",
    ):
        v = getattr(settings, f, None)
        print(f"  {f}: {'SET' if v else 'MISSING'}")

    # Propagate to env for tool modules that read from env directly.
    os.environ["AZURE_OPENAI_ENDPOINT"] = settings.azure_openai_endpoint or ""
    os.environ["AZURE_OPENAI_KEY"] = settings.azure_openai_key or ""
    os.environ["YOUTUBE_API_KEY"] = settings.youtube_api_key or ""
    if settings.apify_token:
        os.environ["APIFY_TOKEN"] = settings.apify_token

    if not settings.database_url:
        print("ERROR: no database_url", file=sys.stderr)
        return 2

    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(db_url, pool_pre_ping=True)

    def session_factory() -> Session:
        return Session(engine)

    print("→ building graph…")
    graph = build_data_graph(session_factory=session_factory).compile()

    state = EricState(
        topic=TOPIC,
        keywords=[],
        max_videos=MAX_VIDEOS,
        region_code="US",
        language="en",
    )

    print(f"→ invoking graph (topic={TOPIC!r}, max_videos={MAX_VIDEOS})…")
    try:
        result = asyncio.run(graph.ainvoke(state))
    except Exception as exc:
        print(f"FATAL: graph failed: {exc}")
        traceback.print_exc()
        return 1

    def g(k, default=None):
        if isinstance(result, dict):
            return result.get(k, default)
        return getattr(result, k, default)

    sr = g("search_results", [])
    dl = g("downloaded", [])
    tr = g("transcripts", {})
    cm = g("comments", {})
    err = g("errors", [])

    print("\n=== GRAPH RESULT ===")
    print(f"  videos found:     {len(sr)}")
    print(f"  audio downloaded: {len(dl)}")
    print(f"  transcripts:      {len(tr)}")
    print(
        f"  comments videos:  {len(cm)} "
        f"(total={sum(len(v) for v in cm.values())})"
    )
    print(f"  errors:           {len(err)}")
    for e in err:
        print(f"    - {e}")

    print("\n=== POSTGRES COUNTS ===")
    with engine.begin() as c:
        for tbl in ("videos", "transcripts", "comments"):
            n = c.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            print(f"  {tbl}: {n}")
        rows = c.execute(
            text(
                "SELECT video_id, title, llm_status FROM videos "
                "ORDER BY discovered_at DESC LIMIT 5"
            )
        ).all()
        for r in rows:
            print(f"    - {r[0]} | {r[2]} | {r[1][:60]}")

    if len(tr) >= 1 and sum(len(v) for v in cm.values()) >= 1:
        print("\n✓ SUCCESS: at least 1 video + transcript + comments persisted.")
        return 0
    print("\n✗ FAIL: did not meet success criteria.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
