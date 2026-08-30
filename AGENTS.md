# AGENTS.md — Cost-Efficient Multi-Model Coding Policy

> Portable policy for OpenAI Codex projects.
> Goal: maximize successful coding output while minimizing unnecessary model usage, reasoning, context, and repeated work.

## 1. Core Principle

Do NOT use the strongest model for every task.

Choose the least expensive/least intensive model that is likely to complete the task correctly on the first or second attempt.

Default priority:

1. **Luna** — simple, mechanical, repetitive, low-risk work
2. **Terra** — normal development, debugging, integration, most feature work
3. **Sol** — difficult architecture, deep debugging, high-risk migrations, tasks where Terra has failed

If the environment does not provide one of these models, use the closest available model and preserve the same escalation strategy.

---

## 2. Model Routing

### Luna — DEFAULT FOR SIMPLE WORK

Use Luna for:

- Small UI changes
- Bootstrap/CSS changes
- Straightforward JavaScript edits
- Renaming variables/functions
- Adding simple validation
- CRUD generated from an established project pattern
- Repetitive endpoint creation
- Seed/sample data
- Formatting
- Documentation
- Simple SQL queries
- Finding references/usages
- Simple syntax errors
- Small isolated bug fixes
- Tests following an already-established pattern
- Boilerplate code
- Mechanical refactoring with clear instructions

Do NOT use Luna for:

- Authentication architecture
- Authorization/permissions architecture
- Database migrations with significant risk
- Complex concurrency/data consistency issues
- Security-sensitive changes
- Large refactors
- Problems with unclear root causes

Recommended reasoning:
- Low for normal tasks
- Medium only when necessary

---

### Terra — PRIMARY DEVELOPMENT MODEL

Use Terra for most real software development:

- New features
- API development
- PHP/backend development
- Database integration
- Authentication implementation
- Authorization implementation when architecture is already established
- Business logic
- ERP modules
- Multi-file changes
- Debugging involving several components
- Integration between frontend/backend/database
- Moderate refactoring
- Performance investigations
- Test implementation
- Code review
- Existing-system modifications

Terra is the default when the task is not obviously simple or exceptionally difficult.

Recommended reasoning:
- Low: straightforward feature implementation
- Medium: normal development/debugging
- High: complex debugging or architecture
- Avoid maximum reasoning unless justified

---

### Sol — ESCALATION MODEL

Use Sol only when the problem justifies it.

Use Sol for:

- Difficult architecture decisions
- Large-system architectural design
- Deep root-cause analysis
- Complex security problems
- Difficult database migrations
- Data corruption/inconsistency investigations
- Complex race conditions/concurrency
- Very difficult performance problems
- Large refactors with high regression risk
- Problems involving many interacting modules
- Tasks where Terra has already failed after a reasonable attempt
- Tasks requiring unusually deep reasoning

Do NOT use Sol for:

- Simple CRUD
- CSS
- Basic forms
- Straightforward SQL
- Renaming
- Documentation
- Boilerplate
- Small bug fixes

Recommended reasoning:
- High/maximum only when necessary

---

## 3. Escalation Rule

Never escalate automatically just because a task is large.

Escalate based on difficulty and failure.

### Level 1 — Luna

Try Luna when the task is mechanical and well-defined.

### Level 2 — Terra

Use Terra when:

- The task requires real design decisions
- Luna cannot solve it
- The task spans multiple layers
- The existing architecture must be understood

### Level 3 — Sol

Use Sol when:

- Terra fails repeatedly
- The root cause remains unclear
- The problem is high-risk
- A major architecture decision is required

Before escalating, preserve the useful investigation/results from the previous model.

Do NOT restart the entire task from scratch if a good investigation already exists.

---

## 4. Context-Budget Rules

Context is a limited resource.

### Never do this:

- Dump the entire repository into the conversation
- Repeatedly paste the same large files
- Re-read unrelated modules
- Ask the model to summarize enormous amounts of irrelevant code
- Keep one conversation alive indefinitely for unrelated tasks

### Prefer this:

1. Identify relevant files.
2. Read only those files.
3. Trace dependencies only as needed.
4. Implement the smallest required change.
5. Verify affected functionality.
6. Summarize the completed state.

When the conversation becomes large, create a concise handoff summary and start a fresh session.

---

## 5. Task Classification

Before doing work, classify the task:

### A — Mechanical
Examples:
- Rename
- Formatting
- CSS
- Simple validation
- Documentation

→ Luna

### B — Standard Development
Examples:
- Feature
- API
- CRUD
- Database integration
- Normal debugging

→ Terra

### C — Complex
Examples:
- Architecture
- Security-critical design
- Difficult debugging
- Data integrity
- Major migration

→ Sol

### D — Unknown

If difficulty is unclear:

→ Start with Terra, investigate first, then escalate if necessary.

---

## 6. Investigation Before Implementation

For non-trivial tasks, do NOT immediately modify code.

First:

1. Inspect relevant files.
2. Identify the current architecture.
3. Trace the execution path.
4. Identify dependencies.
5. Determine the likely root cause.
6. Produce a short implementation plan.
7. Implement only after the plan is clear.

For simple tasks, skip unnecessary investigation.

---

## 7. Avoid Repeated Failed Attempts

If an implementation fails:

Do NOT blindly retry the same approach.

Instead:

1. Inspect the actual error.
2. Determine why the previous attempt failed.
3. Change the approach.
4. If the problem is beyond the current model's reliable capability, escalate.

After two materially different failed attempts on a difficult problem, consider escalating to Terra or Sol.

---

## 8. Minimal-Change Principle

Unless explicitly requested:

- Do not redesign working systems.
- Do not refactor unrelated code.
- Do not rename unrelated files.
- Do not install unnecessary dependencies.
- Do not change database schemas unnecessarily.
- Do not alter authentication.
- Do not change UI styling globally.
- Do not delete existing functionality.

Prefer the smallest safe change that satisfies the requirements.

---

## 9. Verification

After implementation, verify:

- Syntax
- Imports/includes
- Database queries
- References
- Authentication/authorization
- Edge cases
- Existing behavior
- Relevant tests
- API responses
- Frontend/backend integration

For high-risk changes, explicitly test rollback/failure scenarios where practical.

---

## 10. Prompt Efficiency

Prompts should contain:

- Goal
- Relevant constraints
- Acceptance criteria
- Known files/errors
- What must NOT change

Avoid unnecessary background information.

Good:

    Fix the permission check for /admin/users.

    Constraints:
    - Preserve existing role structure.
    - Do not change database schema.
    - API and page access must use the same permission.

    Acceptance:
    - Unauthorized users receive 403.
    - Admin retains access.
    - Sidebar visibility remains unchanged.

Bad:

    Here is the entire project. Please understand everything and fix permissions.

---

## 11. Large Feature Strategy

For large features, split work into phases.

### Phase 1 — Architecture
Terra or Sol depending on complexity.

### Phase 2 — Implementation
Terra.

### Phase 3 — Repetitive/Mechanical Work
Luna where safe.

### Phase 4 — Integration
Terra.

### Phase 5 — Final Audit
Terra; Sol only for high-risk systems.

Do not ask one model to build an entire large system in a single uninterrupted task.

---

## 12. Handoff Format

When switching models, provide a compact handoff:

    ## Task
    ...

    ## Current State
    ...

    ## Files Changed
    ...

    ## Root Cause / Design
    ...

    ## Decisions
    ...

    ## Remaining Work
    ...

    ## Known Issues
    ...

The next model should continue from this state rather than rediscovering the entire project.

---

## 13. Cost Protection Rules

When monthly usage is limited:

1. Prefer Luna for mechanical tasks.
2. Prefer Terra for normal development.
3. Reserve Sol for genuinely difficult work.
4. Avoid maximum reasoning by default.
5. Avoid unnecessarily large context.
6. Avoid repeated retries without diagnosis.
7. Start a new session when the current context becomes bloated.
8. Do not ask the model to analyze unrelated files.
9. Do not regenerate code that already exists.
10. Verify before escalating.

### Emergency Budget Mode

If remaining monthly usage is below approximately 25%:

- Luna → default for simple work
- Terra → important/normal work
- Sol → only critical blockers
- Avoid broad repository analysis
- Avoid large exploratory tasks
- Split large features into small verified tasks

If remaining usage is below approximately 10%:

- Use Luna for mechanical tasks.
- Use Terra only for high-value tasks.
- Avoid exploratory refactors.
- Avoid unnecessary retries.
- Defer non-critical architecture work.

---

## 14. Repository Instructions

Before starting work:

1. Read this AGENTS.md.
2. Inspect project-specific documentation if present.
3. Follow existing architecture and conventions.
4. Never assume a technology or directory structure without checking.

If the project contains another AGENTS.md deeper in the directory tree, follow the more specific instructions for files under that directory, provided they do not conflict with higher-level instructions.

---

## 15. Recommended Portable Project Structure

When appropriate:

    AGENTS.md
    docs/
      architecture.md
      database.md
      api.md
      permissions.md
      workflows.md

Keep architecture knowledge in documentation rather than repeatedly pasting it into prompts.

---

## 16. Final Rule

Optimize for:

**successful task completion per unit of model usage**

—not maximum reasoning on every task.

A cheaper model that completes a task correctly is preferable to a stronger model used unnecessarily.

A stronger model is preferable when its additional reasoning is likely to prevent multiple failed attempts, regressions, or expensive rework.
