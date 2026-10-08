# Handover Protocol for AGENTS.md

Add this section to your project's `AGENTS.md` (for Codex, Gemini, and Antigravity):

```markdown
## Model Handover Protocol (< 5% Limit Threshold)
Whenever operating in Codex, Gemini, or Claude, actively observe remaining context window headroom, token quota, and rate limits.
If remaining tokens or rate limits drop under 5% (or when switching assistants):
1. Halt Immediately: Stop modifying application files or initiating new plan steps to avoid leaving broken/dirty code.
2. Trigger Handover: Run `bash scripts/capture_handover_state.sh` (or `.agents/skills/handover/scripts/capture_handover_state.sh`).
3. Write `HANDOVER.md`: Persist a complete, structured handover document in the project root containing problem description, current behavior, desired behavior, completed milestones, in-flight state, ordered next actions, architectural constraints, and verification status.
4. Provide Continuation Prompt: Conclude with a ready-to-copy continuation prompt formatted for the receiving model to resume seamlessly without losing progress.
```
