"""CLI tool and API endpoint for running sample demonstration cases.

CLI usage:
    python -m backend.tools.run_sample [--template contract|employment|property]

API usage:
    POST /api/tools/run-sample?template=contract
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

SAMPLE_CASES_DIR = Path(__file__).parent / "sample_cases"
VALID_TEMPLATES = ["contract", "employment", "property", "first_amendment", "due_process", "antitrust"]
DEFAULT_TEMPLATE = "contract"


def load_template(template: str) -> dict[str, str]:
    """Load a sample case template by name."""
    if template not in VALID_TEMPLATES:
        msg = f"Unknown template '{template}'. Valid: {VALID_TEMPLATES}"
        raise ValueError(msg)
    template_path = SAMPLE_CASES_DIR / f"{template}.json"
    data: dict[str, str] = json.loads(template_path.read_text())
    return data


async def submit_and_run(
    base_url: str,
    template: str,
) -> dict[str, str]:
    """Submit a sample case and trigger orchestration.

    Returns dict with case_id, monitor_url, and status.
    """
    case_data = load_template(template)

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # Submit the case
        resp = await client.post("/api/cases", json=case_data)
        resp.raise_for_status()
        case_result: dict[str, object] = resp.json()
        case_id = str(case_result["id"])

        # Trigger orchestration
        run_resp = await client.post(f"/api/cases/{case_id}/run")
        run_resp.raise_for_status()

    return {
        "case_id": case_id,
        "template": template,
        "monitor_url": "/monitor",
        "status": "running",
    }


def main() -> None:
    """CLI entry point for running a sample case."""
    parser = argparse.ArgumentParser(
        description="Run a sample legal case through the RalphLex system",
    )
    parser.add_argument(
        "--template",
        choices=VALID_TEMPLATES,
        default=DEFAULT_TEMPLATE,
        help=f"Sample case template to use (default: {DEFAULT_TEMPLATE})",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the RalphLex backend (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    print(f"Loading sample case template: {args.template}")
    result = asyncio.run(submit_and_run(args.base_url, args.template))

    print("\nSample case submitted successfully!")
    print(f"  Case ID:     {result['case_id']}")
    print(f"  Template:    {result['template']}")
    print(f"  Status:      {result['status']}")
    print(f"  Monitor at:  http://localhost:3000{result['monitor_url']}")


if __name__ == "__main__":
    main()
