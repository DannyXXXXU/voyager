#!/usr/bin/env python
"""Inspect Insight rows + failed video detail."""
import os, json
from sqlmodel import create_engine, Session, select
from voyager_db.models import Video, Transcript, Insight, LLMStatus

url = os.environ["DATABASE_URL"]
eng = create_engine(url)
with Session(eng) as s:
    videos = {v.video_id: v for v in s.exec(select(Video)).all()}

    print("=== Videos by status ===")
    for v in videos.values():
        print(f"  {v.llm_status.value:10s}  {v.video_id}  {(v.title or '')[:60]}")
    print()

    insights = s.exec(select(Insight)).all()
    print(f"=== Insights: {len(insights)} rows ===")
    for i in insights:
        pl = i.payload if isinstance(i.payload, dict) else {}
        print(f"\n  id={i.id} video={i.video_id} kind={i.kind.value} model={i.model_name}")
        print(f"  payload preview: {json.dumps(pl, ensure_ascii=False)[:500]}")
