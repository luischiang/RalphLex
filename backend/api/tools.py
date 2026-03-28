"""API endpoints for developer/demo tools."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from backend.api.cases import CaseSubmission, folder_manager
from backend.api.orchestration import _run_orchestration
from backend.models.case import Case
from backend.tools.run_sample import VALID_TEMPLATES, load_template

router = APIRouter()


class RunSampleResponse(BaseModel):
    """Response for running a sample case."""

    case_id: str
    template: str
    monitor_url: str
    status: str


@router.post("/tools/run-sample", status_code=201)
async def run_sample_case(
    background_tasks: BackgroundTasks,
    template: str = Query(
        default="contract",
        description="Sample case template to use",
    ),
) -> RunSampleResponse:
    """Create a sample case from a template and trigger orchestration."""
    if template not in VALID_TEMPLATES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown template '{template}'. Valid: {VALID_TEMPLATES}",
        )

    case_data = load_template(template)
    submission = CaseSubmission(**case_data)

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

    background_tasks.add_task(_run_orchestration, case.id)

    return RunSampleResponse(
        case_id=case.id,
        template=template,
        monitor_url="/monitor",
        status="running",
    )
