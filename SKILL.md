---
name: handover
description: >-
  Halt active work and generate a structured HANDOVER.md file when context window capacity,
  token budget, or rate limits drop under 5%, or when the user requests a model transition
  between Codex, Gemini, or Claude. Captures completed work, in-flight state, next steps,
  and provides an exact continuation prompt for the next model to resume seamlessly.
---

# Handover Skill

Use this skill to execute a clean, seamless handover from one AI model (e.g., OpenAI Codex, Google Gemini, or Anthropic Claude) to another when session limits are nearing exhaustion or when switching assistants.

## When to Trigger This Skill

1. **< 5% Limit Threshold (Automatic Emergency Trigger)**:
   - When remaining context window tokens drop below 5% (or context usage exceeds 95%).
   - When API rate limits, hourly message limits, or token quotas drop below 5% remaining.
   - When the system injects a warning about approaching context exhaustion or truncation.
2. **Explicit User Request**:
   - The user asks for a handover (e.g., `"handover"`, `"hand over to gemini"`, `"hand over to codex"`, `"prepare handover doc"`).
   - The user wants to pause a session and resume in a different tool or model.

---

## Handover Protocol (Step-by-Step)

### Step 1: Emergency Stop (Preserve Workspace Integrity)
- **Immediately STOP** modifying application files, running long builds, or starting new plan steps.
- Do **NOT** attempt to write "just one more function" when tokens are < 5%—partial edits cause syntax errors and broken files.
- If an edit was midway through, finish closing the file cleanly or revert the partial file so the workspace compiles.

### Step 2: Automated State Capture (Save Precious Tokens)
Run the bundled state capture helper to inspect git and workspace status without burning LLM generation tokens:

```bash
bash scripts/capture_handover_state.sh
```

*(Or from workspace root: `bash .agents/skills/handover/scripts/capture_handover_state.sh`).*

### Step 3: Populate `HANDOVER.md` in Workspace Root
Create or overwrite `HANDOVER.md` at the project root using the standard structure defined in
[`templates/HANDOVER_TEMPLATE.md`](./templates/HANDOVER_TEMPLATE.md):

1. **Header & Context**:
   - Original Task & Goal
   - Outgoing Model (e.g., `Gemini 3.8 Flash`, `Codex o3-mini`, `Claude 3.7 Sonnet`)
   - Handover Reason (e.g., `< 5% context limit reached`, `token quota`, `manual switch`)
   - Date & Time
2. **Problem & Behavior Specification**:
   - **Description**: Detailed summary of the task, issue, feature, or request.
   - **Current Behavior**: Current state, observed failure mode, bug, or baseline behavior.
   - **Desired Behavior**: Expected outcome, acceptance criteria, or target behavior.
   - **Key Invariants & Scope**: Critical boundaries, goals, and non-goals.
3. **Current Status & Phase**:
   - Overall task status (e.g., *Phase A Planned, Phase B Step 2 In-Progress*)
4. **Completed Work**:
   - Bulleted list of completed items and created/modified files.
5. **In-Flight / Unfinished Work**:
   - Files currently being edited or partially modified.
   - Any uncommitted diffs or dirty working trees.
6. **Exact Ordered Next Steps**:
   - Numbered, actionable tasks for the incoming model.
   - The exact next file and function/block to touch.
7. **Technical Decisions, Constraints & Gotchas**:
   - Crucial architectural rules followed (e.g., layer boundaries, query conventions).
   - Any bugs diagnosed, edge cases discovered, or pitfalls to avoid.
8. **Verification & Tests**:
   - Passing tests vs pending tests.
   - Commands to validate (e.g., `npm test`, `pytest`, `cargo test`).
9. **Continuation Prompt for Incoming Model**:
   - A crisp, self-contained prompt formatted in a markdown code block that the user can immediately paste into Codex, Gemini, or Claude.

### Step 4: User Notification
Conclude your response immediately with:
1. A concise 2–3 line summary stating that the handover document has been written to `HANDOVER.md`.
2. The copy-pasteable continuation prompt for the next model.

---

## Hard Limit / Process Crash Recovery & Automated Safeguards

Because LLMs cannot natively perceive external API rate limits or credit quotas during execution turns, Codex or other assistants could run until a hard cutoff (`usage_limit_exceeded` / HTTP 429). Three automated safeguards are installed:

1. **Proactive PreToolUse Quota Guard (`codex_quota_guard.py`)**:
   Configured in `hooks.json` (`PreToolUse`). Before each tool execution, it inspects the live session's `rate_limits`. When usage reaches **95%** (leaving < 5% quota), it automatically generates `HANDOVER.md` and halts tool execution with code `2`, preventing a sudden 429 crash.

2. **Automated Turn/Crash Notification Hook (`notify_handover_guard.sh`)**:
   Configured in `~/.codex/config.toml` (`notify`). When a turn ends or the process encounters a hard API error (such as `usage_limit_exceeded`), it automatically extracts the session context and updates `HANDOVER.md` in the workspace root.

3. **Manual / Cross-Model Post-Mortem Extraction**:
   If resuming in Gemini or another tool after an abrupt Codex exit, run:
   ```bash
   python3 scripts/recover_last_codex_session.py
   ```
   This inspects session logs, extracts what the model was doing, redacts secrets/tokens, and recovers the exact context into `HANDOVER.md` without data loss.
