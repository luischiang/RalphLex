export const meta = {
  name: 'ralphlex-build',
  description: 'Build RalphLex story-by-story from prd.json, with independent verification before any story is marked as passing',
  whenToUse: 'Replaces scripts/ralph/ralph.sh. Use to advance the RalphLex PRD autonomously.',
  phases: [
    { title: 'Plan', detail: 'read prd.json, collect pending stories in priority order' },
    { title: 'Implement', detail: 'one agent per story, sequential (single shared working tree)' },
    { title: 'Verify', detail: 'independent auditor confirms the story before flipping passes' },
    { title: 'Report', detail: 'summarize what landed and what remains' },
  ],
}

// How many stories to attempt in one run. Keeps a run bounded and reviewable.
const LIMIT = (args && args.limit) || 3

const PRD = 'scripts/ralph/prd.json'
const PROGRESS = 'scripts/ralph/progress.txt'

const PENDING_SCHEMA = {
  type: 'object',
  required: ['branchName', 'pending'],
  properties: {
    branchName: { type: 'string' },
    pending: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'title', 'description', 'priority'],
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          description: { type: 'string' },
          priority: { type: 'number' },
        },
      },
    },
  },
}

const IMPL_SCHEMA = {
  type: 'object',
  required: ['storyId', 'committed', 'checksPassed', 'summary'],
  properties: {
    storyId: { type: 'string' },
    committed: { type: 'boolean' },
    commitSha: { type: 'string' },
    checksPassed: { type: 'boolean' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    blockers: { type: 'string' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  required: ['storyId', 'satisfied', 'checksRun', 'checksPass', 'reasoning'],
  properties: {
    storyId: { type: 'string' },
    satisfied: { type: 'boolean' },
    checksRun: { type: 'array', items: { type: 'string' } },
    checksPass: { type: 'boolean' },
    issues: { type: 'array', items: { type: 'string' } },
    reasoning: { type: 'string' },
    markedPassing: { type: 'boolean' },
  },
}

phase('Plan')
const plan = await agent(
  `Read ${PRD} in the repository root.

Return the value of "branchName", and the list of stories where "passes" is false,
sorted ascending by "priority". Do not modify any file. Return data only.`,
  { label: 'read-prd', phase: 'Plan', schema: PENDING_SCHEMA },
)

if (!plan || !plan.pending || plan.pending.length === 0) {
  log('No pending stories in the PRD — nothing to build.')
  return { done: true, built: [], remaining: 0 }
}

log(`${plan.pending.length} pending stories; attempting up to ${LIMIT} this run.`)

const queue = plan.pending.slice(0, LIMIT)
const results = []

// Sequential on purpose: every story edits the same working tree, so concurrent
// implementation would corrupt the index. Integrity comes from the verify step,
// not from fan-out.
for (const story of queue) {
  phase('Implement')
  const impl = await agent(
    `You are implementing ONE user story in the RalphLex repository.

Story ${story.id}: ${story.title}
${story.description}

Rules:
- Work on branch "${plan.branchName}"; create it from main if missing.
- Read ${PROGRESS} first — its "Codebase Patterns" section carries forward
  conventions and gotchas from earlier iterations. Follow them.
- Implement only this story. Keep the change focused.
- Run the project's quality gates before committing: pytest, ruff check, and for
  frontend changes npm run lint and npm run build.
- Commit with message: "feat: ${story.id} - ${story.title}"
- Append a progress report to ${PROGRESS}, including a Learnings section, and add
  any genuinely reusable pattern to the Codebase Patterns section at the top.
- Do NOT set "passes": true in ${PRD}. An independent auditor decides that.
- If the quality gates fail and you cannot fix them, do not commit broken code.
  Report checksPassed=false and describe the blocker instead.`,
    { label: `impl:${story.id}`, phase: 'Implement', schema: IMPL_SCHEMA },
  )

  if (!impl || !impl.committed || !impl.checksPassed) {
    log(`${story.id}: implementation did not land (${impl?.blockers || 'agent returned no result'}). Stopping run.`)
    results.push({ story: story.id, status: 'failed', detail: impl?.blockers || 'no result' })
    break
  }

  phase('Verify')
  const verdict = await agent(
    `You are an INDEPENDENT auditor. You did not write this code. Be skeptical.

Story ${story.id}: ${story.title}
Required behaviour: ${story.description}

The implementer claims it is done and committed. Verify that claim yourself:
1. Read the actual diff for the story's commit and the files it touched.
2. Run the quality gates yourself — pytest, ruff check, and for frontend changes
   npm run lint and npm run build. Report the exact commands you ran.
3. Check the implementation against EVERY requirement in the description above.
   A requirement that is stubbed, hardcoded, or silently skipped is NOT satisfied.

Decide:
- If every requirement is met AND the gates pass: set satisfied=true, then set
  "passes": true for ${story.id} in ${PRD} and commit that single change with
  message "chore: mark ${story.id} verified". Set markedPassing=true.
- Otherwise: set satisfied=false, list the concrete issues, change nothing, and
  leave "passes" as false. Set markedPassing=false.

Do not fix the code. Your job is to judge it.`,
    { label: `verify:${story.id}`, phase: 'Verify', schema: VERIFY_SCHEMA },
  )

  if (!verdict || !verdict.satisfied) {
    log(`${story.id}: FAILED verification — ${(verdict?.issues || ['auditor returned no result']).join('; ')}`)
    results.push({ story: story.id, status: 'rejected', issues: verdict?.issues || [], reasoning: verdict?.reasoning })
    break
  }

  log(`${story.id}: verified and marked passing.`)
  results.push({ story: story.id, status: 'passed', summary: impl.summary, checks: verdict.checksRun })
}

phase('Report')
const remaining = plan.pending.length - results.filter(r => r.status === 'passed').length

return {
  branch: plan.branchName,
  attempted: queue.map(s => s.id),
  results,
  remainingStories: remaining,
  allDone: remaining === 0,
}
