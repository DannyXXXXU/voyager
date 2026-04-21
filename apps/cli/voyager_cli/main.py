"""Typer CLI: `voyager eric ...` commands.

Commands:
    submit   enqueue an IngestJob to Service Bus
    status   show video llm_status counts (rich table)
    process  run local LLM subgraph on pending videos
    brief    print latest Brief for a topic
"""
from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from sqlalchemy import create_engine
from sqlmodel import Session, select

from voyager_agents.eric import EricState, build_llm_graph
from voyager_agents.eric.copilot_client import CopilotClaudeClient
from voyager_agents.eric.nodes_llm import StubCopilotClient
from voyager_common import get_settings
from voyager_db.models import Brief, Insight, InsightKind, LLMStatus, Transcript, Video
from voyager_tools.servicebus import IngestJob, IngestProducer

app = typer.Typer(help="Voyager CLI — Eric agent commands.")
eric_app = typer.Typer(help="Eric agent commands.")
app.add_typer(eric_app, name="eric")

console = Console()


def _engine(db_url: str):
    return create_engine(db_url, pool_pre_ping=True)


def _session(db_url: str) -> Session:
    return Session(_engine(db_url))


# --------------------------------------------------------------------------- #
# submit
# --------------------------------------------------------------------------- #
@eric_app.command("submit")
def submit(
    topic: str = typer.Argument(..., help="Topic (e.g. 'west sichuan travel')."),
    keywords: Optional[list[str]] = typer.Option(
        None, "--keywords", "-k", help="Optional extra search keywords (repeat)."
    ),
    max_videos: int = typer.Option(20, "--max-videos"),
    region: str = typer.Option("US", "--region"),
    language: str = typer.Option("en", "--language"),
) -> None:
    """Send an IngestJob to the Service Bus queue."""
    settings = get_settings()
    if not settings.service_bus_conn:
        console.print("[red]service_bus_conn is not configured[/red]")
        raise typer.Exit(code=2)

    job = IngestJob(
        topic=topic,
        keywords=list(keywords or []),
        max_videos=max_videos,
        region_code=region,
        language=language,
    )
    producer = IngestProducer(settings.service_bus_conn)
    asyncio.run(producer.send(job))
    console.print(f"[green]queued[/green] job_id={job.job_id} topic={topic!r}")


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
@eric_app.command("status")
def status(
    job_id: Optional[str] = typer.Option(None, "--job-id", help="(reserved; filters by job in a future milestone)"),
) -> None:
    """Show llm_status counts over videos."""
    settings = get_settings()
    if not settings.database_url:
        console.print("[red]database_url is not configured[/red]")
        raise typer.Exit(code=2)

    with _session(settings.database_url) as s:
        videos = s.exec(select(Video)).all()

    counts = Counter(v.llm_status.value if v.llm_status else "unknown" for v in videos)

    table = Table(title="Video LLM status")
    table.add_column("status", style="cyan")
    table.add_column("count", justify="right", style="magenta")
    for st in ("pending", "processing", "done", "failed", "unknown"):
        table.add_row(st, str(counts.get(st, 0)))
    console.print(table)
    console.print(f"[dim]total videos: {len(videos)}[/dim]")


# --------------------------------------------------------------------------- #
# process
# --------------------------------------------------------------------------- #
@eric_app.command("process")
def process(
    limit: int = typer.Option(20, "--limit"),
    real: bool = typer.Option(
        False, "--real/--stub",
        help="Use real Copilot CLI (--real) or StubCopilotClient (--stub, default).",
    ),
    model: str = typer.Option("claude-sonnet-4.5", "--model"),
) -> None:
    """Run the local LLM subgraph on pending videos.

    Pulls videos with llm_status=pending that have a Transcript row, feeds the
    transcript through the LLM subgraph (hooks → selling points → clusters →
    brief), persists Insight rows, and flips llm_status to done.
    """
    settings = get_settings()
    if not settings.database_url:
        console.print("[red]database_url is not configured[/red]")
        raise typer.Exit(code=2)

    if real:
        client: object = CopilotClaudeClient(model=model)
        model_name = f"copilot-{model}"
        console.print(f"[cyan]using real Copilot CLI[/cyan] model={model}")
    else:
        client = StubCopilotClient()
        model_name = "stub-copilot"
        console.print("[yellow]using StubCopilotClient (offline)[/yellow]")

    graph = build_llm_graph(client).compile()

    with _session(settings.database_url) as s:
        # Only pick pending videos that actually have a transcript, so --limit
        # doesn't get "wasted" on videos where transcription hasn't happened.
        pending = s.exec(
            select(Video)
            .where(Video.llm_status == LLMStatus.pending)
            .where(Video.video_id.in_(select(Transcript.video_id)))
            .limit(limit)
        ).all()
        if not pending:
            console.print("[yellow]no pending videos[/yellow]")
            return

        # Load latest transcript per pending video
        video_ids = [v.video_id for v in pending]
        tr_rows = s.exec(
            select(Transcript).where(Transcript.video_id.in_(video_ids))
        ).all()
        transcripts_by_video: dict[str, Transcript] = {}
        for tr in tr_rows:
            # keep the most recent by created_at
            cur = transcripts_by_video.get(tr.video_id)
            if cur is None or (tr.created_at and cur.created_at and tr.created_at > cur.created_at):
                transcripts_by_video[tr.video_id] = tr

        processable = [v for v in pending if v.video_id in transcripts_by_video]
        skipped = [v.video_id for v in pending if v.video_id not in transcripts_by_video]
        if skipped:
            console.print(f"[dim]skipping {len(skipped)} without transcripts: {skipped[:5]}{'...' if len(skipped) > 5 else ''}[/dim]")

        # Quality gate: reject Whisper-hallucinated / non-English transcripts
        # before burning Copilot tokens on them.
        def _looks_garbage(tr: Transcript) -> str | None:
            text = (tr.text or "").strip()
            if len(text) < 200:
                return f"transcript too short ({len(text)} chars)"
            if tr.language and tr.language.lower() not in ("en", "english", "zh", "chinese"):
                return f"unsupported transcript language: {tr.language!r}"
            # Cheap loop detection: if fewer than 20 unique 20-char shingles, it's a loop.
            shingles = {text[i : i + 20] for i in range(0, max(1, len(text) - 20), 10)}
            if len(shingles) < 20:
                return f"transcript looks looped/hallucinated (only {len(shingles)} unique shingles)"
            return None

        good, bad = [], []
        for v in processable:
            reason = _looks_garbage(transcripts_by_video[v.video_id])
            (bad if reason else good).append((v, reason))
        for v, reason in bad:
            console.print(f"[red]✗[/red] {v.video_id}: {reason}")
            v.llm_status = LLMStatus.failed
            v.llm_error = f"transcript quality gate: {reason}"
        if bad:
            s.commit()
        processable = [v for v, _ in good]
        if not processable:
            console.print("[yellow]no processable videos after quality gate[/yellow]")
            return

        # Flip to processing
        for v in processable:
            v.llm_status = LLMStatus.processing
        s.commit()

        topic = processable[0].source_query or "unknown"
        all_ids: list[str] = []

        from voyager_tools.models import TranscriptResult

        for v in processable:
            tr = transcripts_by_video[v.video_id]
            tr_result = TranscriptResult(
                text=tr.text,
                language=tr.language or "en",
                duration_s=0.0,
            )
            state = EricState(
                topic=v.source_query or topic,
                transcripts={v.video_id: tr_result},
            )
            try:
                out = asyncio.run(graph.ainvoke(state))
            except Exception as e:
                err_text = f"{type(e).__name__}: {e}"[:4000]
                console.print(f"[red]LLM failed for {v.video_id}: {err_text}[/red]")
                v.llm_status = LLMStatus.failed
                v.llm_error = err_text
                s.commit()
                continue

            if isinstance(out, dict):
                out = EricState.model_validate(out)
            for h in out.hooks:
                s.add(Insight(video_id=v.video_id, kind=InsightKind.hook, payload=h, model_name=model_name))
            for p in out.selling_points:
                s.add(Insight(video_id=v.video_id, kind=InsightKind.selling_point, payload=p, model_name=model_name))
            for c in out.clusters:
                s.add(Insight(video_id=v.video_id, kind=InsightKind.cluster, payload=c, model_name=model_name))
            v.llm_status = LLMStatus.done
            all_ids.append(v.video_id)
            s.commit()
            console.print(f"[green]✓[/green] {v.video_id}: hooks={len(out.hooks)} sp={len(out.selling_points)} clusters={len(out.clusters)}")

        if not all_ids:
            console.print("[yellow]no videos processed successfully[/yellow]")
            return

        # Roll up a Brief across all done transcripts for this topic
        rollup_state = EricState(
            topic=topic,
            transcripts={
                vid: TranscriptResult(
                    text=transcripts_by_video[vid].text,
                    language=transcripts_by_video[vid].language or "en",
                    duration_s=0.0,
                )
                for vid in all_ids
            },
        )
        try:
            rollup = asyncio.run(graph.ainvoke(rollup_state))
            if isinstance(rollup, dict):
                rollup = EricState.model_validate(rollup)
            brief_md = rollup.brief_md or f"# Brief: {topic}\n\n(empty)"
        except Exception as e:
            console.print(f"[red]Brief rollup failed: {e}[/red]")
            brief_md = f"# Brief: {topic}\n\n(rollup failed: {e})"

        s.add(Brief(
            topic=topic,
            video_ids=all_ids,
            content_md=brief_md,
            llm_status=LLMStatus.done,
            updated_at=datetime.utcnow(),
        ))
        s.commit()

    console.print(f"[green]processed[/green] {len(all_ids)} videos; brief written for topic={topic!r}")


# --------------------------------------------------------------------------- #
# brief
# --------------------------------------------------------------------------- #
@eric_app.command("brief")
def brief(
    topic: str = typer.Argument(...),
) -> None:
    """Print latest Brief content_md for a topic."""
    settings = get_settings()
    if not settings.database_url:
        console.print("[red]database_url is not configured[/red]")
        raise typer.Exit(code=2)

    with _session(settings.database_url) as s:
        row = s.exec(
            select(Brief).where(Brief.topic == topic).order_by(Brief.created_at.desc())
        ).first()

    if row is None:
        console.print(f"[yellow]no brief for topic[/yellow] {topic!r}")
        raise typer.Exit(code=1)

    console.print(Markdown(row.content_md or f"# {topic}\n\n(empty)"))


if __name__ == "__main__":
    app()
