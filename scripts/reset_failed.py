#!/usr/bin/env python
"""Reset failed videos to pending for retry."""
import os
from sqlmodel import create_engine, Session, select
from voyager_db.models import Video, LLMStatus

eng = create_engine(os.environ["DATABASE_URL"])
with Session(eng) as s:
    failed = s.exec(select(Video).where(Video.llm_status == LLMStatus.failed)).all()
    for v in failed:
        print(f"resetting {v.video_id} (prev error: {v.llm_error})")
        v.llm_status = LLMStatus.pending
        v.llm_error = None
    s.commit()
    print(f"reset {len(failed)} failed videos to pending")
