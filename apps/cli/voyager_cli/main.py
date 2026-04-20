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
from voyager_agents.eric.nodes_llm import StubCopilotClient
from voyager_common import get_settings
from voyager_db.models import Brief, Insight, InsightKind, LLMStatus, Video
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
) -> None:
    """Run the local LLM subgraph on pending videos (stub client)."""
    settings = get_settings()
    if not settings.database_url:
        console.print("[red]database_url is not configured[/red]")
        raise typer.Exit(code=2)

    client = StubCopilotClient()
    graph = build_llm_graph(client).compile()

    with _session(settings.database_url) as s:
        pending = s.exec(
            select(Video).where(Video.llm_status == LLMStatus.pending).limit(limit)
        ).all()

        if not pending:
            console.print("[yellow]no pending videos[/yellow]")
            return

        # Flip to processing
        for v in pending:
            v.llm_status = LLMStatus.processing
        s.commit()

        topic = pending[0].source_query or "unknown"
        all_ids: list[str] = []

        for v in pending:
            state = EricState(topic=v.source_query or topic)
            out = asyncio.run(graph.ainvoke(state))
            # LangGraph returns dict; unwrap via EricState
            if isinstance(out, dict):
                out = EricState.model_validate(out)
            for h in out.hooks:
                s.add(
                    Insight(
                        video_id=v.video_id,
                        kind=InsightKind.hook,
                        payload=h,
                        model_name="stub-copilot",
                    )
                )
            for p in out.selling_points:
                s.add(
                    Insight(
                        video_id=v.video_id,
                        kind=InsightKind.selling_point,
                        payload=p,
                        model_name="stub-copilot",
                    )
                )
            for c in out.clusters:
                s.add(
                    Insight(
                        video_id=v.video_id,
                        kind=InsightKind.cluster,
                        payload=c,
                        model_name="stub-copilot",
                    )
                )
            v.llm_status = LLMStatus.done
            all_ids.append(v.video_id)

        # Roll up a Brief for this topic across all done videos
        done_state = EricState(topic=topic)
        rollup = asyncio.run(graph.ainvoke(done_state))
        if isinstance(rollup, dict):
            rollup = EricState.model_validate(rollup)
        brief = Brief(
            topic=topic,
            video_ids=all_ids,
            content_md=rollup.brief_md or f"# Brief: {topic}\n\n(stub)",
            llm_status=LLMStatus.done,
            updated_at=datetime.utcnow(),
        )
        s.add(brief)
        s.commit()

    console.print(f"[green]processed[/green] {len(all_ids)} videos; brief written")


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
