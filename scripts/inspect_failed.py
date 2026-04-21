#!/usr/bin/env python
import os, textwrap
from sqlmodel import create_engine, Session, select
from voyager_db.models import Video, Transcript, LLMStatus

eng = create_engine(os.environ["DATABASE_URL"])
with Session(eng) as s:
    v = s.exec(select(Video).where(Video.llm_status == LLMStatus.failed)).first()
    print(f"video: {v.video_id}  title: {v.title}")
    print(f"ERROR:\n{v.llm_error}")
    print()
    tr = s.exec(select(Transcript).where(Transcript.video_id == v.video_id)).first()
    if tr:
        print(f"transcript lang={tr.language} len={len(tr.text)}")
        print(f"first 400: {tr.text[:400]}")
        print(f"last 400:  {tr.text[-400:]}")
    else:
        print("NO TRANSCRIPT")
