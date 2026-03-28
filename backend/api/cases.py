"""Case intake REST API for external agent submission."""

import json

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
