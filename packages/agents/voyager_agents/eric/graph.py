"""LangGraph graph builders for the Eric agent."""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from voyager_agents.eric.nodes_data import (
    node_download_audio,
    node_fetch_comments,
    node_fetch_metadata,
    node_persist,
    node_plan_search,
    node_transcribe,
)
from voyager_agents.eric.nodes_llm import (
    CopilotClient,
    node_cluster_insights,
    node_extract_hooks,
    node_extract_selling_points,
    node_write_brief,
)
from voyager_agents.eric.state import EricState


def build_data_graph(session_factory: Any = None) -> StateGraph:
    """Build the cloud-worker data subgraph.

    Parameters
    ----------
    session_factory:
        Optional callable returning a SQLModel/SQLAlchemy Session. If provided,
        the persist node will use it; otherwise callers must inject a session
        at invocation time via `config={"configurable": {"session": ...}}`.

    Returns
    -------
    An uncompiled StateGraph. Callers call `.compile()` to get the Runnable.
    """
    g: StateGraph = StateGraph(EricState)
    g.add_node("plan_search", node_plan_search)
    g.add_node("fetch_metadata", node_fetch_metadata)
    g.add_node("download_audio", node_download_audio)
    g.add_node("transcribe", node_transcribe)
    g.add_node("fetch_comments", node_fetch_comments)

    def _persist(state: EricState) -> EricState:
        if session_factory is None:
            # Allow the compiled graph to be built without a session; callers
            # that invoke the data subgraph must provide one by re-building.
            raise RuntimeError(
                "build_data_graph called without session_factory; "
                "cannot run persist node"
            )
        session = session_factory()
        try:
            return node_persist(state, session)
        finally:
            close = getattr(session, "close", None)
            if callable(close):
                close()

    g.add_node("persist", _persist)

    g.set_entry_point("plan_search")
    g.add_edge("plan_search", "fetch_metadata")
    g.add_edge("fetch_metadata", "download_audio")
    g.add_edge("download_audio", "transcribe")
    g.add_edge("transcribe", "fetch_comments")
    g.add_edge("fetch_comments", "persist")
    g.add_edge("persist", END)
    return g


def build_llm_graph(client: CopilotClient) -> StateGraph:
    """Build the local-CLI LLM subgraph, bound to a CopilotClient."""
    g: StateGraph = StateGraph(EricState)

    async def _hooks(state: EricState) -> EricState:
        return await node_extract_hooks(state, client)

    async def _points(state: EricState) -> EricState:
        return await node_extract_selling_points(state, client)

    async def _cluster(state: EricState) -> EricState:
        return await node_cluster_insights(state, client)

    async def _brief(state: EricState) -> EricState:
        return await node_write_brief(state, client)

    g.add_node("extract_hooks", _hooks)
    g.add_node("extract_selling_points", _points)
    g.add_node("cluster_insights", _cluster)
    g.add_node("write_brief", _brief)

    g.set_entry_point("extract_hooks")
    g.add_edge("extract_hooks", "extract_selling_points")
    g.add_edge("extract_selling_points", "cluster_insights")
    g.add_edge("cluster_insights", "write_brief")
    g.add_edge("write_brief", END)
    return g
