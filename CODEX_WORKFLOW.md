# CODEX_WORKFLOW.md — Efficient Codex Workflow

> Portable workflow for OpenAI Codex projects.
> Goal: maximize successful work while protecting monthly usage, context, and reasoning budget.

## 1. Golden Rule

Do not optimize for maximum model power.

Optimize for:

**successful result ÷ model usage**

Use the cheapest model capable of completing the task reliably.

Default:

- Luna → simple/mechanical
- Terra → normal development
- Sol → difficult/high-risk problems

See `AGENTS.md` for detailed model routing.

---

## 2. Before Starting Any Task

Classify the task.

### Small
Examples:
- CSS
- Bootstrap
- Rename
- Formatting
- Simple validation
- Documentation
- Simple SQL
- Existing-pattern CRUD

Use Luna.

### Medium
Examples:
- New feature
- API endpoint
- Database integration
- Business logic
- Multi-file bug
- Authentication implementation
- Normal refactoring

Use Terra.

### Large / Difficult
Examples:
- Architecture
- Security-critical changes
- Data integrity
- Difficult migrations
- Complex concurrency
- Deep debugging
- Large refactors

Use Terra first for investigation, then Sol if justified.

---

## 3. The Investigation Rule

For anything that is not obviously simple:

Do not immediately ask for implementation.

Use:

1. Inspect relevant files.
2. Trace the current behavior.
3. Identify the root cause/design.
4. Produce a concise plan.
5. Implement.
6. Verify.

This prevents expensive failed implementations.

For simple tasks, skip unnecessary investigation.

---

## 4. The Smallest-Useful-Context Rule

Never give Codex the entire repository unless absolutely necessary.

Instead:

1. Identify the feature.
2. Find the relevant entry point.
3. Trace dependencies.
4. Read only the files needed.
5. Modify only affected files.

Avoid repeatedly loading:

- Entire repositories
- Large generated files
- Large logs
- Unrelated modules
- Repeated copies of the same code

Context is a budget.

---

## 5. Task Decomposition

Do not give Codex a huge instruction such as:

> Build the entire ERP.

Split it.

Example:

### Task 1
Design roles and permissions.

### Task 2
Implement database structure.

### Task 3
Implement backend permission checks.

### Task 4
Implement admin UI.

### Task 5
Connect navigation visibility.

### Task 6
Test authorization.

### Task 7
Audit the entire module.

Each completed task becomes a stable checkpoint.

---

## 6. One Objective Per Task

A task should have one primary objective.

Good:

> Fix the production-order permission check.

Bad:

> Fix permissions, redesign the dashboard, optimize SQL, clean the JavaScript, and improve the UI.

Mixed tasks increase context and regression risk.

---

## 7. Acceptance Criteria

Every medium/large task should have acceptance criteria.

Example:

    Goal:
    Fix production-order authorization.

    Acceptance criteria:
    - Admin can access production orders.
    - Authorized users can access them.
    - Unauthorized users receive 403.
    - Direct URL access is protected.
    - API endpoints are protected.
    - Existing roles continue working.

Codex should verify every criterion before declaring the task complete.

---

## 8. Don't Repeat Failed Attempts

If a solution fails:

### First failure

Inspect the actual error.

Do not immediately retry the same solution.

### Second failure

Change the approach.

### Third failure on a difficult task

Stop and reassess.

Consider escalating:

Luna → Terra → Sol

Do not waste monthly usage on repeated blind attempts.

---

## 9. Model Escalation

### Luna → Terra

Escalate when:

- Requirements become ambiguous.
- Multiple files/modules interact.
- Business logic is involved.
- Luna fails to understand the architecture.
- The first solution fails and the cause is not obvious.

### Terra → Sol

Escalate when:

- Root cause remains unclear.
- Terra fails after reasonable attempts.
- Database integrity is at risk.
- Security is high-risk.
- Architecture requires deep reasoning.
- Multiple subsystems interact in a difficult way.

Do not escalate just because the task is large.

---

## 10. Reasoning Escalation

Use the lowest appropriate reasoning level.

### Low

Use for:
- Mechanical edits
- Simple implementation
- Straightforward fixes
- Boilerplate

### Medium

Use for:
- Normal features
- Backend work
- Database integration
- APIs
- Standard debugging

### High

Use for:
- Complex debugging
- Architecture
- Security
- Data integrity
- Difficult migrations

### Maximum

Reserve for genuinely difficult problems.

Do not use maximum reasoning by default.

---

## 11. Context Management

Monitor the context indicator.

### Under 40%

Normal operation.

### 40–60%

Start avoiding unnecessary file reads and repeated explanations.

### 60–75%

Prefer focused tasks.

Avoid unrelated work in the same session.

Create a concise handoff summary if switching tasks.

### Above 75%

Strongly consider starting a new session.

Create:

    SESSION_HANDOFF.md

containing:

- Current task
- Completed work
- Files changed
- Important decisions
- Current errors
- Remaining work
- Next recommended step

Then start a fresh session.

---

## 12. Never Mix Unrelated Work

Do not turn one session into:

1. Fix login
2. Build reports
3. Redesign dashboard
4. Debug Excel import
5. Change database
6. Add a new module
7. Fix CSS

Each unrelated task adds context and increases the chance of wasted reasoning.

Use separate sessions when practical.

---

## 13. Use Checkpoints

After a meaningful feature is complete:

1. Verify it.
2. Save/commit the changes.
3. Record what changed.
4. Start the next task from a clean state.

Recommended checkpoint:

    ## Completed
    ...

    ## Files Changed
    ...

    ## Tests
    ...

    ## Known Issues
    ...

---

## 14. Prompt Template — Simple Task

Use:

    Task:
    [specific change]

    Constraints:
    - Change only what is necessary.
    - Preserve existing functionality.

    Acceptance:
    - [criterion]
    - [criterion]

For simple tasks, do not add unnecessary background.

---

## 15. Prompt Template — Medium Task

Use:

    Task:
    [feature]

    First inspect the existing implementation.

    Identify:
    - relevant files
    - current flow
    - dependencies
    - likely implementation point

    Then implement the smallest safe solution.

    Constraints:
    - preserve existing behavior
    - no unrelated refactoring
    - no unnecessary dependencies

    Acceptance criteria:
    - [criterion]
    - [criterion]

    Finally verify the implementation.

---

## 16. Prompt Template — Difficult Task

Use:

    Task:
    [problem]

    Do not modify files yet.

    First:
    1. Inspect the relevant architecture.
    2. Trace the execution/data flow.
    3. Identify possible root causes.
    4. Compare the possible solutions.
    5. Recommend the safest solution.

    Wait for implementation only after the approach is clear.

This is especially useful before using Sol.

---

## 17. Handoff Between Models

When changing models, do not make the next model rediscover everything.

Provide:

    # Handoff

    ## Goal
    ...

    ## Current State
    ...

    ## Investigation
    ...

    ## Root Cause
    ...

    ## Files Changed
    ...

    ## Decisions
    ...

    ## Failed Approaches
    ...

    ## Remaining Work
    ...

The next model should continue from this information.

---

## 18. Avoid Giant Prompts

Do not paste enormous amounts of code when Codex can inspect the repository.

Prefer:

> Inspect `app/roles`, `api/auth`, and the permissions tables and determine how authorization currently works.

Instead of pasting hundreds of lines.

Use pasted code only when:

- The code is not available in the workspace.
- A specific snippet is needed.
- The task depends on external content.

---

## 19. Avoid Asking for Unnecessary Explanations

If the task is:

> Add a button.

Do not ask for a 2,000-word explanation.

Use:

> Implement it and briefly summarize the changed files.

Long explanations consume output/context without improving the code.

---

## 20. Don't Regenerate Existing Code

If a module already works:

Do not ask Codex to rewrite the entire module to add one feature.

Instead:

> Identify the minimal insertion point and modify only the required functionality.

---

## 21. Protect the Database

For database changes:

1. Inspect the schema.
2. Find all usages.
3. Determine compatibility impact.
4. Plan the migration.
5. Implement.
6. Verify existing queries.
7. Check rollback implications.

For high-risk migrations, use Terra/Sol.

Never blindly modify production-like data.

---

## 22. Protect Authentication and Permissions

For authentication/authorization changes:

- Check backend enforcement.
- Do not rely only on hidden UI elements.
- Check direct URL access.
- Check API access.
- Check role inheritance.
- Check existing administrator behavior.
- Test unauthorized scenarios.

These tasks deserve Terra at minimum.

---

## 23. Budget Mode

When monthly usage becomes limited:

### Above 50%

Normal policy.

### 25–50%

- Luna for simple tasks.
- Terra for important development.
- Sol only for high-value difficult problems.
- Avoid broad exploratory tasks.

### 10–25%

- Luna becomes the default.
- Terra only for important features/blockers.
- Sol only for critical issues.
- Avoid large refactors.
- Avoid unnecessary experimentation.

### Below 10%

- Focus only on critical work.
- Avoid exploratory development.
- Avoid repeated attempts.
- Prefer deterministic/mechanical tasks.
- Defer non-critical work.

---

## 24. Daily Usage Protection

If the project has a monthly usage limit, do not spend a large portion of it in one session.

If a task starts consuming unusually large context or repeated reasoning:

STOP.

Ask:

1. Is the task actually difficult?
2. Am I giving unnecessary context?
3. Is the model repeating failed approaches?
4. Should I split the task?
5. Should I escalate?
6. Should I start a fresh session?

---

## 25. The 3-Attempt Rule

For a normal bug:

### Attempt 1
Implement the most likely fix.

### Attempt 2
Inspect the failure and correct the approach.

### Attempt 3
Reassess architecture/root cause.

After that, escalate or stop.

Do not continue generating slightly different versions indefinitely.

---

## 26. Final Verification Checklist

Before declaring a task complete:

- [ ] Requirements implemented
- [ ] Acceptance criteria checked
- [ ] Relevant files reviewed
- [ ] Syntax checked
- [ ] References checked
- [ ] Database queries checked
- [ ] Permissions checked if applicable
- [ ] Existing functionality preserved
- [ ] No unnecessary dependencies added
- [ ] No unrelated files modified
- [ ] Relevant tests run
- [ ] Remaining issues documented

---

## 27. Recommended Session Lifecycle

Use this lifecycle:

    START
      ↓
    Classify task
      ↓
    Select least expensive capable model
      ↓
    Inspect only relevant context
      ↓
    Implement smallest safe change
      ↓
    Verify
      ↓
    Checkpoint
      ↓
    Next task / new session

For difficult tasks:

    START
      ↓
    Investigate
      ↓
    Terra
      ↓
    Evaluate difficulty
      ↓
    Sol only if justified
      ↓
    Implement
      ↓
    Verify
      ↓
    Checkpoint

---

## 28. Core Philosophy

The best Codex workflow is not:

> "Always use the strongest model."

It is:

> "Use the least expensive model that can reliably solve the current problem, and escalate only when the evidence says you should."

Protect:

1. Context
2. Reasoning budget
3. Monthly usage
4. Time
5. Code stability

A successful first attempt is usually cheaper than several failed attempts.

A focused task is usually cheaper than a giant task.

A clean session is usually cheaper than an overloaded session.
