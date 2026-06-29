"""LangGraph graph: S1..S6 with bounded self-repair loops + cross-model verification.

    START -> S1 intake -> S2 retrieval -> S3 exemption ->
             S3.5 citation-critic --(repair<=2)--> S3
                                  --(ok|escalate)--> S4 redaction ->
             S4.5 redaction-critic --(repair<=2)--> S4
                                   --(ok|escalate)--> S5 draft -> S6 PIO approval (HITL) -> END

UiPath reads `graph` (compiled, no checkpointer — the runtime injects persistence).
eval/run.py imports `builder` and compiles it with an in-memory checkpointer so the S6
interrupt is observable locally.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from rti_sahayak.nodes.s1_intake import s1_intake
from rti_sahayak.nodes.s2_retrieval import s2_retrieval
from rti_sahayak.nodes.s3_exemption import s3_exemption
from rti_sahayak.nodes.s3_5_citation_critic import s3_5_citation_critic
from rti_sahayak.nodes.s4_redaction import s4_redaction
from rti_sahayak.nodes.s4_5_redaction_critic import s4_5_redaction_critic
from rti_sahayak.nodes.s5_drafter import s5_drafter
from rti_sahayak.nodes.s6_approval import s6_approval
from rti_sahayak.state import RTIState


class GraphInput(TypedDict, total=False):
    rti_id: str
    request_text: str
    received_date: str       # ISO yyyy-mm-dd
    records_ref: str         # which synthetic record set to load


class GraphOutput(TypedDict, total=False):
    draft: dict
    dispositions: list
    redactions: list
    confidence: float
    flags: list
    escalate: bool
    human_decision: dict
    audit: list


def _route_after_citation(state: RTIState) -> str:
    return "repair" if state.get("route_citation") == "repair" else "continue"


def _route_after_redaction(state: RTIState) -> str:
    return "repair" if state.get("route_redaction") == "repair" else "continue"


def build_graph() -> StateGraph:
    b = StateGraph(RTIState, input_schema=GraphInput, output_schema=GraphOutput)

    b.add_node("s1_intake", s1_intake)
    b.add_node("s2_retrieval", s2_retrieval)
    b.add_node("s3_exemption", s3_exemption)
    b.add_node("s3_5_citation_critic", s3_5_citation_critic)
    b.add_node("s4_redaction", s4_redaction)
    b.add_node("s4_5_redaction_critic", s4_5_redaction_critic)
    b.add_node("s5_drafter", s5_drafter)
    b.add_node("s6_approval", s6_approval)

    b.add_edge(START, "s1_intake")
    b.add_edge("s1_intake", "s2_retrieval")
    b.add_edge("s2_retrieval", "s3_exemption")
    b.add_edge("s3_exemption", "s3_5_citation_critic")
    b.add_conditional_edges(
        "s3_5_citation_critic", _route_after_citation,
        {"repair": "s3_exemption", "continue": "s4_redaction"},
    )
    b.add_edge("s4_redaction", "s4_5_redaction_critic")
    b.add_conditional_edges(
        "s4_5_redaction_critic", _route_after_redaction,
        {"repair": "s4_redaction", "continue": "s5_drafter"},
    )
    b.add_edge("s5_drafter", "s6_approval")
    b.add_edge("s6_approval", END)
    return b


builder = build_graph()
graph = builder.compile()
