# RalphLex

Autonomous multi-agent legal reasoning system for pre-trial dispute resolution.

RalphLex simulates judicial proceedings through iterative AI agent loops. External agents (representing companies, insurers, or individuals) submit cases via a REST API. The system instantiates three internal roles -- claimant agent, respondent agent, and court/judge agent -- that argue, counter-argue, and evaluate until reaching a resolution.

## Architecture

```
                    External Agents
                         |
                    POST /api/cases
                         |
                   +-----v------+
                   |  FastAPI    |  REST API (port 8000)
                   |  Backend    |  + Swagger docs at /docs
                   +-----+------+
                         |
              +----------v-----------+
              |  Case Orchestrator   |
              |  (Ralph Loop)        |
              +----------+-----------+
                         |
         +---------------+----------------+
         |               |                |
   +-----v-----+  +-----v------+  +------v------+
   |  Claimant  |  | Respondent |  |   Court     |
   |   Agent    |  |   Agent    |  |   Agent     |
   +-----+-----+  +-----+------+  +------+------+
         |               |                |
         +-------+-------+       +--------+--------+
                 |                |                  |
          Argument Loop    Adversarial Review   MCDA Scoring
          (converge or     (opinion -> challenge  (weighted
           max iters)       -> reconcile)         multi-criteria)
                                                       |
                                               +-------v--------+
                                               |  Escalation    |
                                               |  Engine        |
                                               +-------+--------+
                                                       |
                                                 Judicial Hierarchy
                                              (First Instance -> Appeals
                                               -> Superior -> Supreme)

   +-------------------+     +-------------------+
   | Legal Reference   |     | React Frontend    |
   | Database (SQLite) |     | (port 3000)       |
   | + Internet        |     | Monitoring        |
   |   Fallback        |     | Dashboard         |
   +-------------------+     +-------------------+
```

## The Ralph Loop

The core pipeline for each case:

1. **Case Intake** -- External agent submits facts and supporting materials via POST /api/cases
2. **Argument Iteration** -- Claimant and respondent agents alternate structured arguments until positions converge (similarity > 0.85 threshold) or max iterations reached
3. **Legal Reference Retrieval** -- SQLite-backed keyword + TF-IDF search for precedents and laws, with internet fallback when local results are insufficient
4. **Court Evaluation** -- Three-phase adversarial review:
   - Phase 1: Consistency analysis + compliance check + preliminary opinion
   - Phase 2: Adversarial self-challenge (counter-opinion)
   - Phase 3: Reconciliation into final decision
5. **MCDA Scoring** -- Multi-Criteria Decision Analysis rates each side on 5 criteria (evidentiary strength, legal consistency, procedural validity, precedent alignment, appeal likelihood) with configurable weights
6. **Escalation Check** -- Determines if case should escalate to a higher judicial level based on constitutional questions, conflicting precedents, or procedural irregularities
7. **Resolution or Escalation** -- Either produces final output or re-runs the loop at the next judicial level

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- An Anthropic API key

### Installation

```bash
# Clone the repository
git clone <repo-url> && cd RalphLex

# Install Python dependencies
make install
# Or manually:
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install frontend dependencies
cd frontend && npm install && cd ..

# Configure environment
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

### Running

```bash
# Start both backend and frontend
make dev

# Or start them separately:
make dev-backend   # FastAPI on http://localhost:8000
make dev-frontend  # React on http://localhost:3000
```

### API Documentation

Once the backend is running, interactive Swagger documentation is available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## How External Agents Interact with the API

### 1. Submit a Case

```bash
curl -X POST http://localhost:8000/api/cases \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Contract Breach: Acme vs. Globex",
    "facts": "Acme Corp contracted Globex to deliver 500 units by Jan 1. No goods were delivered. Acme seeks damages under UCC Article 2.",
    "party_role": "claimant",
    "supporting_materials": "Invoice #12345, signed delivery schedule"
  }'
```

Response (201):
```json
{
  "id": "a1b2c3d4-...",
  "title": "Contract Breach: Acme vs. Globex",
  "status": "pending",
  "judicial_level": "first_instance",
  ...
}
```

### 2. Trigger Orchestration

```bash
curl -X POST http://localhost:8000/api/cases/{case_id}/run
```

Response (202):
```json
{
  "case_id": "a1b2c3d4-...",
  "status": "accepted",
  "message": "Orchestration started in background"
}
```

### 3. Poll for Status

```bash
curl http://localhost:8000/api/cases/{case_id}/status
```

Response:
```json
{
  "case_id": "a1b2c3d4-...",
  "status": "running",
  "phase": "arguing",
  "judicial_level": "First Instance",
  "message": "Running argument loop at First Instance"
}
```

### 4. Retrieve Final Result

```bash
curl http://localhost:8000/api/cases/{case_id}/outputs/final_result.json
```

Response includes all 10 output fields:
- `judicial_stage` -- Final judicial level at resolution
- `arguments_summary` -- Claimant and respondent argument summaries
- `referenced_precedents` -- Legal precedents cited
- `referenced_laws` -- Applicable statutes and regulations
- `court_evaluation` -- Full court evaluation with consistency analysis, compliance check, adversarial review
- `escalation_decisions` -- List of escalation events (if any)
- `mcda_scoring` -- Criteria scores, weighted totals, winner prediction
- `predicted_winner` -- Party with strongest position
- `confidence_estimate` -- Confidence in the prediction (0-1)
- `full_reasoning_trace` -- Step-by-step reasoning log

### 5. Other Useful Endpoints

```bash
# List all cases
curl http://localhost:8000/api/cases

# Get case timeline
curl http://localhost:8000/api/cases/{case_id}/timeline

# Get argument iterations
curl http://localhost:8000/api/cases/{case_id}/iterations

# Run a sample case
curl -X POST "http://localhost:8000/api/tools/run-sample?template=contract"
# Templates: contract, employment, property
```

## Judicial Hierarchy

Cases are evaluated at the First Instance level by default. The escalation engine can promote cases through higher courts:

| Level | Scope | Escalation Triggers |
|-------|-------|-------------------|
| **First Instance** | Individual disputes | Constitutional questions, conflicting precedents |
| **Appeals Court** | Reviews lower court decisions | Procedural irregularities, legal interpretation errors |
| **Superior Court** | Significant legal questions | Conflicting appellate decisions, public interest |
| **Supreme Court** | Final authority | Fundamental constitutional matters |

Escalation criteria are configured in `backend/config/judicial_hierarchy.json`.

## MCDA Framework

The Multi-Criteria Decision Analysis scores each party on five weighted criteria:

| Criterion | Default Weight | Description |
|-----------|---------------|-------------|
| Evidentiary Strength | 0.25 | Quality and sufficiency of evidence |
| Legal Consistency | 0.25 | Internal consistency of legal arguments |
| Procedural Validity | 0.20 | Compliance with procedural requirements |
| Precedent Alignment | 0.20 | Alignment with established precedent |
| Appeal Likelihood | 0.10 | Likelihood of successful appeal |

Weights are configurable in `backend/evaluation/weights.json`. Raw scores (1-10) are normalized to 0-1 and weighted to produce a predicted winner with confidence estimate.

## Project Structure

```
RalphLex/
  backend/
    agents/          # LLM agents (base, claimant, respondent, court)
    api/             # FastAPI route handlers
    config/          # JSON config files (judicial hierarchy)
    evaluation/      # MCDA scoring module and weights
    legal_db/        # SQLite legal reference store + seed data
    models/          # Pydantic data models
    services/        # Business logic (case folders, argument loop, convergence, escalation)
    tools/           # CLI tools and sample case templates
    orchestrator.py  # Main case orchestration pipeline
    config.py        # Environment settings (pydantic-settings)
    app.py           # FastAPI application setup
  frontend/
    src/
      pages/         # React pages (CaseList, CaseSubmit, CaseDetail, Monitor)
      components/    # Reusable components (Nav, StatusBadge)
      api.ts         # Typed API client
      App.tsx        # Router and layout
  tests/             # pytest test suite
  data/cases/        # Case data (created at runtime)
  Makefile           # Dev commands
  pyproject.toml     # Python project config
```

## Development

### Quality Checks

```bash
make lint       # Ruff linting and formatting
make typecheck  # mypy type checking
make test       # pytest test suite
```

### Running Tests

```bash
# Run all tests
.venv/bin/pytest

# Run specific test file
.venv/bin/pytest tests/test_e2e.py

# Run with verbose output
.venv/bin/pytest -v
```

### Frontend Type Checking

```bash
cd frontend && npx tsc --noEmit
```

## Troubleshooting

- **"ANTHROPIC_API_KEY not set"** -- Copy `.env.example` to `.env` and add your key
- **Backend won't start** -- Ensure you activated the venv: `source .venv/bin/activate`
- **Frontend API calls fail** -- The Vite dev server proxies `/api` to port 8000; ensure the backend is running
- **Tests fail with import errors** -- Install in dev mode: `pip install -e ".[dev]"`
- **mypy errors on Anthropic SDK types** -- Use `cast()` and `hasattr()` guards for SDK union types (see codebase patterns)
- **Port already in use** -- Kill existing processes: `lsof -ti:8000 | xargs kill` or `lsof -ti:3000 | xargs kill`

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key |
| `MODEL_NAME` | `claude-sonnet-4-20250514` | Claude model to use |
| `MAX_TOKENS` | `4096` | Max tokens per LLM call |
| `DEFAULT_TEMPERATURE` | `0.7` | LLM temperature |
| `MAX_RETRIES` | `3` | LLM retry count |
| `RETRY_BASE_DELAY` | `1.0` | Base delay for exponential backoff |
