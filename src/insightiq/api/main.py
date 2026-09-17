from __future__ import annotations

from pathlib import Path
from threading import Thread

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
    InvestigationStatus,
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
        api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        return OpenAIDecisionProvider(settings.openai_model, api_key=api_key)
    return DeterministicDecisionProvider()


def build_investigator() -> Investigator:
    return Investigator(
        registry,
        build_provider(),
        max_steps=settings.max_steps,
        max_tool_calls=settings.max_tool_calls,
        confidence_threshold=settings.confidence_threshold,
    )


app = FastAPI(
    title="InsightIQ",
    version="0.4.0",
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
        "openai_configured": bool(settings.openai_api_key),
        "data_backend": settings.data_backend,
        "tools": registry.names,
    }


@app.post("/investigations", response_model=InvestigationReport)
def create_investigation(request: InvestigationRequest) -> InvestigationReport:
    investigator = build_investigator()
    state, report = investigator.investigate(request.question)
    repository.save(InvestigationRecord(state=state, report=report, graph=build_graph(state)))
    return report


@app.post("/investigations/start", status_code=202)
def start_investigation(request: InvestigationRequest) -> dict:
    investigator = build_investigator()
    state = investigator.create_state(request.question)
    repository.save_state(state.model_copy(deep=True))

    def run() -> None:
        try:
            final_state, report = investigator.investigate(
                request.question,
                state=state,
                progress_callback=repository.save_state,
                step_delay=0.25,
            )
            repository.save(
                InvestigationRecord(
                    state=final_state,
                    report=report,
                    graph=build_graph(final_state),
                )
            )
        except Exception:
            state.status = InvestigationStatus.FAILED
            repository.save_state(state)
            raise

    Thread(target=run, daemon=True, name=f"insightiq-{state.investigation_id}").start()
    return {"investigation_id": state.investigation_id, "status": state.status}


@app.get("/tools")
def list_tools() -> dict:
    return {"tools": registry.describe()}


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
    record = get_record(investigation_id)
    return record.graph or build_graph(record.state)


@app.get("/investigations/{investigation_id}/report", response_model=InvestigationReport)
def get_report(investigation_id: str) -> InvestigationReport:
    report = get_record(investigation_id).report
    if not report:
        raise HTTPException(status_code=409, detail="Investigation is still running.")
    return report
