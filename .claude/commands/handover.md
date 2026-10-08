---
description: Halt active edits, capture workspace git state, and generate HANDOVER.md for seamless model transition
---

Execute the Handover Protocol:
1. **Emergency Stop**: Stop editing application files immediately to preserve workspace integrity.
2. **Capture Git State**: Run the state capture script to inspect branches, status, and unstaged diffs:
   ```bash
   bash scripts/capture_handover_state.sh || bash .agents/skills/handover/scripts/capture_handover_state.sh
   ```
3. **Generate `HANDOVER.md`**: Create or update `HANDOVER.md` in the project root following the 9-section standard in `templates/HANDOVER_TEMPLATE.md`:
   - **Section 1: Executive Context**: Task description, Outgoing Model ("Claude Code"), Handover Reason, Timestamp, Branch.
   - **Section 2: Problem & Behavior Specification**:
     - `Description`: The problem, feature, or request.
     - `Current Behavior`: Current state, error logs, or baseline behavior.
     - `Desired Behavior`: Expected outcome and acceptance criteria.
     - `Key Invariants & Scope`: Guidelines and constraints.
   - **Section 3: Current Execution Status**: Active phase and 1-2 sentence status.
   - **Section 4: What Was Completed**: Bulleted achievements and touched files.
   - **Section 5: In-Flight Workspace State & Git Diffs**: Output from `capture_handover_state.sh`.
   - **Section 6: Ordered Next Steps**: Numbered action items with exact target files.
   - **Section 7: Technical Decisions & Invariants**: Architecture patterns and constraints.
   - **Section 8: Verification & Testing Status**: Passing vs pending tests (`npm test`, `pytest`, `cargo test`, etc.).
   - **Section 9: Continuation Prompt**: A clean, ready-to-copy continuation prompt formatted for the receiving model (Gemini, Codex, or another Claude session).
4. **Conclusion**: Conclude with a concise 2-sentence confirmation and the copy-pasteable continuation prompt.
