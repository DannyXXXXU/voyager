"""FastAPI application exposing Eric agent endpoints.

Routes:
    POST /eric/jobs                 — enqueue IngestJob
    GET  /eric/videos               — list videos (filter by llm_status)
    GET  /eric/videos/{video_id}    — video + transcript + comments
    GET  /eric/briefs               — list briefs
    GET  /eric/briefs/{brief_id}    — brief with content_md
    GET  /healthz                   — liveness + dep checks
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any, Iterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlmodel import Session, select

from voyager_common import Settings, get_settings
from voyager_db.models import Brief, Comment, LLMStatus, Transcript, Video
from voyager_tools.servicebus import IngestJob, IngestProducer

logger = logging.getLogger(__name__)

app = FastAPI(title="Voyager API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Dependency injection
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _cached_settings() -> Settings:
    return get_settings()


def settings_dep() -> Settings:
    return _cached_settings()


@lru_cache(maxsize=1)
def _engine_for(db_url: str):
    return create_engine(db_url, pool_pre_ping=True)


def get_db_session(
    settings: Settings = Depends(settings_dep),
) -> Iterator[Session]:
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="database_url not configured")
    engine = _engine_for(settings.database_url)
    with Session(engine) as session:
        yield session


def get_producer(settings: Settings = Depends(settings_dep)) -> IngestProducer:
    if not settings.service_bus_conn:
        raise HTTPException(status_code=503, detail="service_bus_conn not configured")
    return IngestProducer(settings.service_bus_conn)


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #
class JobCreateRequest(BaseModel):
    topic: str
    keywords: list[str] = Field(default_factory=list)
    max_videos: int = 20
    region_code: str = "US"
    language: str = "en"


class JobCreateResponse(BaseModel):
    job_id: str
    status: str = "queued"


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.post("/eric/jobs", response_model=JobCreateResponse)
async def create_job(
    req: JobCreateRequest,
    producer: IngestProducer = Depends(get_producer),
) -> JobCreateResponse:
    job = IngestJob(
        topic=req.topic,
        keywords=req.keywords,
        max_videos=req.max_videos,
        region_code=req.region_code,
        language=req.language,
    )
    await producer.send(job)
    return JobCreateResponse(job_id=job.job_id, status="queued")


@app.get("/eric/videos")
def list_videos(
    llm_status: Optional[LLMStatus] = None,
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[dict[str, Any]]:
    stmt = select(Video)
    if llm_status is not None:
        stmt = stmt.where(Video.llm_status == llm_status)
    stmt = stmt.limit(limit)
    rows = session.exec(stmt).all()
    return [_video_to_dict(v) for v in rows]


@app.get("/eric/videos/{video_id}")
def get_video(
    video_id: str,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    transcript = session.exec(
        select(Transcript).where(Transcript.video_id == video_id)
    ).first()
    comments = session.exec(
        select(Comment).where(Comment.video_id == video_id)
    ).all()
    return {
        "video": _video_to_dict(video),
        "transcript": _transcript_to_dict(transcript) if transcript else None,
        "comments": [_comment_to_dict(c) for c in comments],
    }


@app.get("/eric/briefs")
def list_briefs(
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[dict[str, Any]]:
    stmt = select(Brief).order_by(Brief.created_at.desc()).limit(limit)
    rows = session.exec(stmt).all()
    return [_brief_to_dict(b, include_content=False) for b in rows]


@app.get("/eric/briefs/{brief_id}")
def get_brief(
    brief_id: int,
    session: Session = Depends(get_db_session),
) -> dict[str, Any]:
    brief = session.get(Brief, brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="brief not found")
    return _brief_to_dict(brief, include_content=True)


@app.get("/healthz")
def healthz(
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    db_ok = False
    sb_ok = bool(settings.service_bus_conn)
    if settings.database_url:
        try:
            engine = _engine_for(settings.database_url)
            with Session(engine) as session:
                session.exec(select(1))
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("healthz db check failed: %s", exc)
    return {
        "status": "ok",
        "db": "ok" if db_ok else "fail",
        "service_bus": "ok" if sb_ok else "fail",
        "env": settings.env,
    }


# --------------------------------------------------------------------------- #
# Row → dict helpers
# --------------------------------------------------------------------------- #
def _video_to_dict(v: Video) -> dict[str, Any]:
    return {
        "video_id": v.video_id,
        "title": v.title,
        "channel_id": v.channel_id,
        "channel_title": v.channel_title,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "view_count": v.view_count,
        "like_count": v.like_count,
        "duration_s": v.duration_s,
        "thumbnail_url": v.thumbnail_url,
        "lang": v.lang,
        "region": v.region,
        "source_query": v.source_query,
        "llm_status": v.llm_status.value if v.llm_status else None,
        "discovered_at": v.discovered_at.isoformat() if v.discovered_at else None,
    }


def _transcript_to_dict(t: Transcript) -> dict[str, Any]:
    return {
        "id": t.id,
        "video_id": t.video_id,
        "text": t.text,
        "language": t.language,
        "model_name": t.model_name,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _comment_to_dict(c: Comment) -> dict[str, Any]:
    return {
        "id": c.id,
        "video_id": c.video_id,
        "author": c.author,
        "text": c.text,
        "like_count": c.like_count,
        "published_at": c.published_at.isoformat() if c.published_at else None,
    }


def _brief_to_dict(b: Brief, include_content: bool = False) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": b.id,
        "topic": b.topic,
        "video_ids": b.video_ids,
        "llm_status": b.llm_status.value if b.llm_status else None,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }
    if include_content:
        d["content_md"] = b.content_md
    return d


# Silence unused-import warnings for asyncio (kept for uvicorn reload path).
_ = asyncio
