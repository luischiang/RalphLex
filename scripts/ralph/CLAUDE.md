# Ralph Agent Instructions

You are an autonomous coding agent building **RalphLex** — an autonomous multi-agent legal reasoning system for pre-trial dispute resolution.

## Project Context

### What RalphLex Is
A framework that simulates judicial proceedings through iterative AI agent loops. External agents (representing companies, insurers, or individuals) submit cases. The system instantiates three internal roles — claimant agent, respondent agent, and court/judge agent — that argue, counter-argue, and evaluate until reaching a resolution. The goal is to reduce the need for formal trial by producing a validated, precedent-backed resolution with confidence scoring.

### Tech Stack
- **Backend:** Python with FastAPI (backend/ directory), running on port 8000
- **Frontend:** React with Vite + TypeScript + Tailwind CSS (frontend/ directory), running on port 3000
- **LLM:** Anthropic Claude API (via the `anthropic` Python SDK)
- **Database:** SQLite for legal reference storage
- **No cloud dependencies** — everything runs on a single machine

### Architecture Principles
- **Agent-first design:** Primary users are other AI agents, not humans. The REST API is the main interface; the web app is for monitoring.
- **Case folder isolation:** Each case gets its own directory under data/cases/{case_id}/ with config/, state/, iterations/, and outputs/ subdirectories storing JSON files.
- **Iterative convergence:** Claimant and respondent agents alternate arguments until their positions stabilize (convergence detection), then the court agent evaluates.
- **Adversarial judicial review:** The court agent must NOT be a simple summarizer. It generates a preliminary opinion, then challenges it with a counter-opinion, then reconciles into a final decision.
- **MCDA scoring:** Multi-Criteria Decision Analysis using weighted criteria (evidentiary strength, legal consistency, procedural validity, precedent alignment, appeal likelihood) to score positions and predict outcomes.
- **Judicial hierarchy:** Cases can escalate through levels (First Instance -> Appeals -> Superior -> Supreme Court) based on constitutional questions, conflicting precedents, or procedural grounds.
- **Legal reference database:** SQLite-backed store of precedents and laws with keyword/TF-IDF search and internet fallback when local results are insufficient.

### Key Design Decisions
- Use Pydantic models for all data structures
- Use asyncio for orchestration (FastAPI BackgroundTasks for long-running case processing)
- Proxy frontend /api requests to backend via Vite config
- Store MCDA weights in a configurable JSON file
- Judicial hierarchy defined in a JSON config file
- Environment variables for API keys and settings (pydantic-settings)

## Your Task

1. Read the PRD at `prd.json` (in the same directory as this file)
2. Read the progress log at `progress.txt` (check Codebase Patterns section first)
3. Check you're on the correct branch from PRD `branchName`. If not, check it out or create from main.
4. Pick the **highest priority** user story where `passes: false`
5. Implement that single user story
6. Run quality checks (e.g., typecheck, lint, test - use whatever your project requires)
7. Update CLAUDE.md files if you discover reusable patterns (see below)
8. If checks pass, commit ALL changes with message: `feat: [Story ID] - [Story Title]`
9. Update the PRD to set `passes: true` for the completed story
10. Append your progress to `progress.txt`

## Progress Report Format

APPEND to progress.txt (never replace, always append):
```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered (e.g., "this codebase uses X for Y")
  - Gotchas encountered (e.g., "don't forget to update Z when changing W")
  - Useful context (e.g., "the evaluation panel is in component X")
---
```

The learnings section is critical - it helps future iterations avoid repeating mistakes and understand the codebase better.

## Consolidate Patterns

If you discover a **reusable pattern** that future iterations should know, add it to the `## Codebase Patterns` section at the TOP of progress.txt (create it if it doesn't exist). This section should consolidate the most important learnings:

```
## Codebase Patterns
- Example: Use `sql<number>` template for aggregations
- Example: Always use `IF NOT EXISTS` for migrations
- Example: Export types from actions.ts for UI components
```

Only add patterns that are **general and reusable**, not story-specific details.

## Update CLAUDE.md Files

Before committing, check if any edited files have learnings worth preserving in nearby CLAUDE.md files:

1. **Identify directories with edited files** - Look at which directories you modified
2. **Check for existing CLAUDE.md** - Look for CLAUDE.md in those directories or parent directories
3. **Add valuable learnings** - If you discovered something future developers/agents should know:
   - API patterns or conventions specific to that module
   - Gotchas or non-obvious requirements
   - Dependencies between files
   - Testing approaches for that area
   - Configuration or environment requirements

**Examples of good CLAUDE.md additions:**
- "When modifying X, also update Y to keep them in sync"
- "This module uses pattern Z for all API calls"
- "Tests require the dev server running on PORT 3000"
- "Field names must match the template exactly"

**Do NOT add:**
- Story-specific implementation details
- Temporary debugging notes
- Information already in progress.txt

Only update CLAUDE.md if you have **genuinely reusable knowledge** that would help future work in that directory.

## Quality Requirements

- ALL commits must pass your project's quality checks (typecheck, lint, test)
- Do NOT commit broken code
- Keep changes focused and minimal
- Follow existing code patterns

## Browser Testing (If Available)

For any story that changes UI, verify it works in the browser if you have browser testing tools configured (e.g., via MCP):

1. Navigate to the relevant page
2. Verify the UI changes work as expected
3. Take a screenshot if helpful for the progress log

If no browser tools are available, note in your progress report that manual browser verification is needed.

## Stop Condition

After completing a user story, check if ALL stories have `passes: true`.

If ALL stories are complete and passing, reply with:
<promise>COMPLETE</promise>

If there are still stories with `passes: false`, end your response normally (another iteration will pick up the next story).

## Important

- Work on ONE story per iteration
- Commit frequently
- Keep CI green
- Read the Codebase Patterns section in progress.txt before starting
