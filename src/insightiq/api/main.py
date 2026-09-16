from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from insightiq.agent.investigator import Investigator
from insightiq.agent.providers import DeterministicDecisionProvider, OpenAIDecisionProvider
from insightiq.config import get_settings
from insightiq.logging_config import configure_logging
from insightiq.models import (
    GraphExport,
    InvestigationReport,
    InvestigationRequest,
    InvestigationState,
)
from insightiq.storage import InMemoryRepository, InvestigationRecord
from insightiq.tools.factory import build_registry
from insightiq.trust.graph import build_graph

configure_logging()
settings = get_settings()
repository = InMemoryRepository()
registry = build_registry(settings)


def build_provider():
    if settings.agent_mode == "openai":
        return OpenAIDecisionProvider(settings.openai_model)
    return DeterministicDecisionProvider()


app = FastAPI(
    title="InsightIQ",
    version="0.3.0",
    description="Evidence-grounded autonomous business investigation agent",
)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    candidates = [
        Path.cwd() / "frontend" / "index.html",
        Path(__file__).resolve().parents[4] / "frontend" / "index.html",
    ]
    for path in candidates:
        if path.exists():
            return FileResponse(path)
    raise HTTPException(status_code=404, detail="Demo UI not found.")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "agent_mode": settings.agent_mode,
        "model": settings.openai_model if settings.agent_mode == "openai" else None,
        "data_backend": settings.data_backend,
        "tools": registry.names,
    }


@app.post("/investigations", response_model=InvestigationReport)
def create_investigation(request: InvestigationRequest) -> InvestigationReport:
    investigator = Investigator(
        registry,
        build_provider(),
        max_steps=settings.max_steps,
        max_tool_calls=settings.max_tool_calls,
        confidence_threshold=settings.confidence_threshold,
    )
    state, report = investigator.investigate(request.question)
    repository.save(InvestigationRecord(state=state, report=report, graph=build_graph(state)))
    return report


def get_record(investigation_id: str) -> InvestigationRecord:
    record = repository.get(investigation_id)
    if not record:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    return record


@app.get("/investigations/{investigation_id}", response_model=InvestigationState)
def get_investigation(investigation_id: str) -> InvestigationState:
    return get_record(investigation_id).state


@app.get("/investigations/{investigation_id}/evidence")
def get_evidence(investigation_id: str) -> dict:
    state = get_record(investigation_id).state
    return {"investigation_id": investigation_id, "evidence": state.evidence}


@app.get("/investigations/{investigation_id}/graph", response_model=GraphExport)
def get_graph(investigation_id: str) -> GraphExport:
    return get_record(investigation_id).graph


@app.get("/investigations/{investigation_id}/report", response_model=InvestigationReport)
def get_report(investigation_id: str) -> InvestigationReport:
    return get_record(investigation_id).report
