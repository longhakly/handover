# Handover Protocol for Claude Code

Add this section to your project's `CLAUDE.md` or `~/.claude/CLAUDE.md`:

```markdown
## Handover Protocol
When the user asks to "handover", "hand over to gemini/codex", or when context limits approach exhaustion:
1. Immediately halt modifying application files.
2. Run `bash scripts/capture_handover_state.sh` (or `bash .agents/skills/handover/scripts/capture_handover_state.sh`) to inspect git state.
3. Generate `HANDOVER.md` in the project root following `.agents/skills/handover/templates/HANDOVER_TEMPLATE.md`.
4. Include the Problem Specification (Description, Current Behavior, Desired Behavior), touched files, clean git diffs, and ordered next steps.
5. Provide a copy-pasteable continuation prompt formatted for the receiving model (Gemini or Codex).
```
