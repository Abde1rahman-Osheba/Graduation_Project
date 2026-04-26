"""
LangGraph workflow: transcript → summary → HR → technical → compliance → decision.
Resumability: question generation and scheduling live in the service layer; this graph
runs after a transcript exists (or with an empty transcript — low confidence).
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.interview_intelligence.nodes import (
    node_compliance,
    node_decision_support,
    node_hr_evaluation,
    node_summarize,
    node_technical_evaluation,
)
from app.agents.interview_intelligence.state import InterviewGraphState


def create_interview_analysis_graph():
    workflow = StateGraph(InterviewGraphState)
    workflow.add_node("summarize_transcript", node_summarize)
    workflow.add_node("hr_evaluation", node_hr_evaluation)
    workflow.add_node("technical_evaluation", node_technical_evaluation)
    workflow.add_node("compliance_guardrail", node_compliance)
    workflow.add_node("decision_support", node_decision_support)

    workflow.set_entry_point("summarize_transcript")
    workflow.add_edge("summarize_transcript", "hr_evaluation")
    workflow.add_edge("hr_evaluation", "technical_evaluation")
    workflow.add_edge("technical_evaluation", "compliance_guardrail")
    workflow.add_edge("compliance_guardrail", "decision_support")
    workflow.add_edge("decision_support", END)
    return workflow.compile()


interview_analysis_app = create_interview_analysis_graph()
