# Session Handover Document

> **Handover Notice**: Generated automatically when session limit dropped below 5% or model transition was requested.

---

## 1. Executive Context

- **Original Task**: {Short description of the user request}
- **Outgoing Model**: {e.g. Gemini 3.8 Flash / OpenAI Codex / Claude 3.7 Sonnet}
- **Handover Reason**: {e.g. Context headroom < 5% / Quota limit reached / User requested switch}
- **Timestamp**: {ISO timestamp or current date & time}
- **Branch / Worktree**: {Git branch name or workspace directory}

---

## 2. Problem & Behavior Specification

- **Description**: {Detailed description of the task, issue, feature, or user request}
- **Current Behavior**: {What is currently happening, existing bug/limitation, or baseline state before changes}
- **Desired Behavior**: {Expected outcome, acceptance criteria, target state, or intended behavior}
- **Key Invariants & Scope**: {Strict constraints, boundaries, or non-goals}

---

## 3. Current Execution Status

- **Plan Stage**: {e.g. Phase B - Step 2 of 4}
- **Progress Summary**: {1-2 sentences summarizing current state}

---

## 4. What Was Completed

- [x] {Task 1}: {Details of what was achieved}
- [x] {Task 2}: {Details of what was achieved}

### Files Created or Modified
- `{filepath}`: {Summary of changes}
- `{filepath}`: {Summary of changes}

---

## 5. In-Flight & Uncommitted Work

- **Currently Touched Files**:
  - `{filepath}`: {Status: clean / dirty / partially edited}
- **Pending Diffs**:
  - {Notes on any uncommitted edits or temporary state}

---

## 6. Ordered Next Steps (Immediate Action Required)

1. **Step {N} (Immediate)**: {Exact action the incoming model must take first}
   - Target file: `{filepath}`
   - Action: {Specific function, schema, or route to implement}
2. **Step {N+1}**: {Follow-up task}
3. **Step {N+2}**: {Verification / tests}

---

## 7. Technical Decisions, Invariants & Gotchas

- **Architecture Rules Applied**: {e.g. Service layer boundaries, typed schemas, repository patterns}
- **Discovered Quirks / Edge Cases**: {Any bugs found or important implementation nuances}
- **Strict Constraints**: {Project guidelines (e.g. AGENTS.md, CLAUDE.md, etc.) that must be preserved}

---

## 8. Verification & Testing Status

- **Tests Passing**: `{command or test paths that passed}`
- **Tests Pending / Untested**: `{command or test paths to run next}`
- **Lint / Build Status**: `{status}`

---

## 9. Continuation Prompt for Incoming Model

```markdown
You are continuing a task handed over from another model.
Please read `HANDOVER.md` in the project root to understand full context, current progress, and technical invariants.

Current immediate objective:
- Pick up at Step {N}: {Brief description of next task}
- Target file(s): `{filepath}`
- Ensure all repository guidelines and invariants are respected.

Proceed directly with executing Step {N}.
```
