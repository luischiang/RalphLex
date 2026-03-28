"""Case intake REST API for external agent submission."""

import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.models.case import Case, CaseStatus, JudicialLevel
from backend.services.case_folder import CaseFolderManager

router = APIRouter()

folder_manager = CaseFolderManager()


class CaseSubmission(BaseModel):
    """Request body for submitting a new case."""

    title: str = Field(..., min_length=1, description="Case title")
    facts: str = Field(..., min_length=1, description="Case facts")
    party_role: str = Field(
        ...,
        pattern="^(claimant|respondent)$",
        description="Role of the submitting party: claimant or respondent",
    )
    supporting_materials: str | None = Field(None, description="Additional supporting materials")


class CaseResponse(BaseModel):
    """Response for a single case."""

    id: str
    title: str
    facts: str
    claimant_input: str | None
    respondent_input: str | None
    status: CaseStatus
    judicial_level: JudicialLevel
    created_at: str
    updated_at: str


class CaseListItem(BaseModel):
    """Summary item for case listing."""

    id: str
    title: str
    status: CaseStatus
    judicial_level: JudicialLevel
    created_at: str


def _case_to_response(case: Case) -> CaseResponse:
    return CaseResponse(
        id=case.id,
        title=case.title,
        facts=case.facts,
        claimant_input=case.claimant_input,
        respondent_input=case.respondent_input,
        status=case.status,
        judicial_level=case.judicial_level,
        created_at=case.created_at.isoformat(),
        updated_at=case.updated_at.isoformat(),
    )


def _case_to_list_item(case: Case) -> CaseListItem:
    return CaseListItem(
        id=case.id,
        title=case.title,
        status=case.status,
        judicial_level=case.judicial_level,
        created_at=case.created_at.isoformat(),
    )


@router.post("/cases", status_code=201)
async def create_case(submission: CaseSubmission) -> CaseResponse:
    """Submit a new case from an external agent."""
    case = Case(
        title=submission.title,
        facts=submission.facts,
        claimant_input=(
            submission.supporting_materials if submission.party_role == "claimant" else None
        ),
        respondent_input=(
            submission.supporting_materials if submission.party_role == "respondent" else None
        ),
    )
    folder_manager.create(case)
    return _case_to_response(case)


@router.get("/cases")
async def list_cases() -> list[CaseListItem]:
    """List all cases with status."""
    case_ids = folder_manager.list_cases()
    cases: list[CaseListItem] = []
    for case_id in case_ids:
        case = folder_manager.load(case_id)
        cases.append(_case_to_list_item(case))
    return cases


@router.get("/cases/{case_id}")
async def get_case(case_id: str) -> CaseResponse:
    """Retrieve current case state from the case folder."""
    try:
        case = folder_manager.load(case_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return _case_to_response(case)


@router.get("/cases/{case_id}/iterations")
async def get_iterations(case_id: str) -> list[dict[str, object]]:
    """Return all iteration argument files for a case."""
    case_dir = folder_manager.case_dir(case_id)
    iters_dir = case_dir / "iterations"
    if not iters_dir.exists():
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    results: list[dict[str, object]] = []
    for f in sorted(iters_dir.glob("round_*.json")):
        data: dict[str, object] = json.loads(f.read_text())
        results.append(data)
    return results


class TimelineEntry(BaseModel):
    """A single entry in the case timeline."""

    timestamp: str
    phase: str
    event: str
    details: dict[str, object] = Field(default_factory=dict)
    is_escalation: bool = False


@router.get("/cases/{case_id}/timeline")
async def get_timeline(case_id: str) -> list[TimelineEntry]:
    """Return the iteration history with timestamps and phase details."""
    case_dir = folder_manager.case_dir(case_id)
    if not (case_dir / "config" / "case.json").exists():
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    entries: list[TimelineEntry] = []

    # Case creation
    try:
        case = folder_manager.load(case_id)
        entries.append(
            TimelineEntry(
                timestamp=case.created_at.isoformat(),
                phase="created",
                event=f"Case '{case.title}' created",
                details={"judicial_level": case.judicial_level.value},
            )
        )
    except Exception:
        pass

    # Iteration files
    iters_dir = case_dir / "iterations"
    if iters_dir.exists():
        for f in sorted(iters_dir.glob("round_*.json")):
            data: dict[str, object] = json.loads(f.read_text())
            ts = str(data.get("timestamp", ""))
            role = str(data.get("role", "unknown"))
            iteration = data.get("iteration", 0)
            content = str(data.get("content", ""))
            entries.append(
                TimelineEntry(
                    timestamp=ts or _file_mtime_iso(f),
                    phase="arguing",
                    event=f"Round {iteration} - {role} argument",
                    details={
                        "role": role,
                        "iteration": iteration,
                        "content_preview": content[:200],
                    },
                )
            )

    # Court evaluation
    court_file = case_dir / "outputs" / "court_evaluation.json"
    if court_file.exists():
        court_data: dict[str, object] = json.loads(court_file.read_text())
        entries.append(
            TimelineEntry(
                timestamp=_file_mtime_iso(court_file),
                phase="evaluating",
                event="Court evaluation completed",
                details={
                    "has_escalation_recommendation": bool(
                        court_data.get("escalation_recommendation")
                    ),
                },
            )
        )

    # MCDA scoring
    mcda_file = case_dir / "outputs" / "mcda_scoring.json"
    if mcda_file.exists():
        mcda_data: dict[str, object] = json.loads(mcda_file.read_text())
        entries.append(
            TimelineEntry(
                timestamp=_file_mtime_iso(mcda_file),
                phase="scoring",
                event="MCDA scoring completed",
                details={
                    "predicted_winner": mcda_data.get("predicted_winner"),
                    "confidence": mcda_data.get("confidence"),
                },
            )
        )

    # Escalation events from archived level directories
    outputs_dir = case_dir / "outputs"
    if outputs_dir.exists():
        for level_dir in sorted(outputs_dir.iterdir()):
            if level_dir.is_dir() and level_dir.name.startswith("level_"):
                level_name = level_dir.name.replace("level_", "").replace("_", " ").title()
                entries.append(
                    TimelineEntry(
                        timestamp=_file_mtime_iso(level_dir),
                        phase="escalating",
                        event=f"Escalated from {level_name}",
                        details={"archived_level": level_dir.name},
                        is_escalation=True,
                    )
                )

    # Final result
    final_file = case_dir / "outputs" / "final_result.json"
    if final_file.exists():
        final_data: dict[str, object] = json.loads(final_file.read_text())
        esc_decisions = final_data.get("escalation_decisions", [])
        entries.append(
            TimelineEntry(
                timestamp=_file_mtime_iso(final_file),
                phase="completed",
                event="Case resolved",
                details={
                    "judicial_stage": final_data.get("judicial_stage"),
                    "predicted_winner": final_data.get("predicted_winner"),
                    "confidence_estimate": final_data.get("confidence_estimate"),
                    "escalation_count": len(esc_decisions)
                    if isinstance(esc_decisions, list)
                    else 0,
                },
            )
        )

    # Sort by timestamp
    entries.sort(key=lambda e: e.timestamp)
    return entries


def _file_mtime_iso(path: "os.PathLike[str]") -> str:
    """Get file modification time as ISO string."""
    from datetime import UTC, datetime

    mtime = os.path.getmtime(path)
    return datetime.fromtimestamp(mtime, tz=UTC).isoformat()


@router.get("/cases/{case_id}/outputs/{filename}")
async def get_output(case_id: str, filename: str) -> dict[str, object]:
    """Return a specific output file for a case."""
    case_dir = folder_manager.case_dir(case_id)
    output_file = case_dir / "outputs" / filename
    if not output_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Output {filename} not found for case {case_id}",
        )
    result: dict[str, object] = json.loads(output_file.read_text())
    return result
