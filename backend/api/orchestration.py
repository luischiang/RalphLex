"""Orchestration API endpoints for running and monitoring cases."""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.models.case import CaseStatus
from backend.orchestrator import (
    CaseOrchestrator,
    OrchestratorProgress,
    get_progress,
)
from backend.services.case_folder import CaseFolderManager

router = APIRouter()

folder_manager = CaseFolderManager()
orchestrator = CaseOrchestrator(folder_manager=folder_manager)


class RunResponse(BaseModel):
    """Response for triggering case orchestration."""

    case_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    """Response for case orchestration status."""

    case_id: str
    status: str
    phase: str
    judicial_level: str
    message: str


async def _run_orchestration(case_id: str) -> None:
    """Background task that runs the orchestration pipeline."""
    await orchestrator.run(case_id)


@router.post("/cases/{case_id}/run", status_code=202)
async def run_case(case_id: str, background_tasks: BackgroundTasks) -> RunResponse:
    """Trigger case orchestration as a background task."""
    try:
        case = folder_manager.load(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    if case.status == CaseStatus.running:
        raise HTTPException(
            status_code=409,
            detail=f"Case {case_id} is already running",
        )

    background_tasks.add_task(_run_orchestration, case_id)

    return RunResponse(
        case_id=case_id,
        status="accepted",
        message="Orchestration started in background",
    )


@router.get("/cases/{case_id}/status")
async def get_case_status(case_id: str) -> StatusResponse:
    """Get current phase and progress of case orchestration."""
    try:
        case = folder_manager.load(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    progress: OrchestratorProgress | None = get_progress(case_id)

    if progress:
        return StatusResponse(
            case_id=case_id,
            status=case.status.value,
            phase=progress.phase,
            judicial_level=progress.judicial_level,
            message=progress.message,
        )

    return StatusResponse(
        case_id=case_id,
        status=case.status.value,
        phase="pending" if case.status == CaseStatus.pending else "unknown",
        judicial_level=case.judicial_level.value,
        message="No orchestration progress available",
    )
