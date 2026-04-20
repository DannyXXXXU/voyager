"""Graph compile smoke tests."""
from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from voyager_agents.eric.graph import build_data_graph, build_llm_graph
from voyager_agents.eric.nodes_llm import StubCopilotClient


def test_build_data_graph_compiles() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)

    def session_factory() -> Session:
        return Session(engine)

    graph = build_data_graph(session_factory=session_factory)
    compiled = graph.compile()
    assert compiled is not None


def test_build_llm_graph_compiles() -> None:
    graph = build_llm_graph(StubCopilotClient())
    compiled = graph.compile()
    assert compiled is not None


def test_build_data_graph_without_session_still_compiles() -> None:
    graph = build_data_graph(session_factory=None)
    compiled = graph.compile()
    assert compiled is not None
