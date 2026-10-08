#!/usr/bin/env python3
"""
generate_handover.py

Universal HANDOVER.md generator for all AI coding agents (Claude Code, Gemini, Codex, Cursor).
Can be run:
1. By an agent (Claude, Gemini, Codex) via terminal command.
2. Directly by a developer from the command line:
   python3 scripts/generate_handover.py "Task description"
"""

import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

def capture_git_state(workspace_root):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "capture_handover_state.sh"),
        os.path.join(workspace_root, ".agents/skills/handover/scripts/capture_handover_state.sh"),
        os.path.join(workspace_root, "scripts/capture_handover_state.sh"),
        os.path.expanduser("~/.agents/skills/handover/scripts/capture_handover_state.sh"),
    ]
    for script_path in candidates:
        if os.path.exists(script_path):
            try:
                res = subprocess.run(["bash", script_path], cwd=workspace_root, capture_output=True, text=True, check=True)
                return res.stdout.strip()
            except Exception:
                pass

    # Direct fallback inspection
    reports = []
    if os.path.exists(os.path.join(workspace_root, ".git")):
        try:
            branch = subprocess.check_output(["git", "-C", workspace_root, "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
            status = subprocess.check_output(["git", "-C", workspace_root, "status", "-s"], text=True).strip()
            reports.append(f"### Repository: `{os.path.basename(workspace_root)}`\n- **Branch**: `{branch}`\n- **Status**: {status if status else 'Clean'}")
        except Exception:
            pass
    else:
        for entry in sorted(os.listdir(workspace_root)):
            sub = os.path.join(workspace_root, entry)
            if os.path.isdir(sub) and os.path.exists(os.path.join(sub, ".git")):
                try:
                    branch = subprocess.check_output(["git", "-C", sub, "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
                    status = subprocess.check_output(["git", "-C", sub, "status", "-s"], text=True).strip()
                    reports.append(f"### Repository: `{entry}`\n- **Branch**: `{branch}`\n- **Status**: {status if status else 'Clean'}")
                except Exception:
                    continue
    return "\n\n".join(reports) if reports else "No git changes detected."

def sanitize_secrets(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"Bearer\s+eyJ[A-Za-z0-9_\-\.]+", "Bearer [REDACTED_JWT]", text)
    text = re.sub(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+", "[REDACTED_JWT]", text)
    text = re.sub(r"(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-\.]{12,}['\"]", "[REDACTED_SECRET]", text, flags=re.IGNORECASE)
    return text

def detect_validation_commands(workspace_root):
    commands = []
    if os.path.exists(os.path.join(workspace_root, "package.json")):
        commands.append("npm test # or pnpm test / yarn test / bun test")
        commands.append("npm run build # or typecheck")
    if any(os.path.exists(os.path.join(workspace_root, f)) for f in ["pyproject.toml", "requirements.txt", "Pipfile", "setup.py"]):
        commands.append("pytest")
        if os.path.exists(os.path.join(workspace_root, "pyproject.toml")):
            commands.append("ruff check # or flake8 / mypy")
    if os.path.exists(os.path.join(workspace_root, "Cargo.toml")):
        commands.append("cargo test")
        commands.append("cargo check")
    if os.path.exists(os.path.join(workspace_root, "go.mod")):
        commands.append("go test ./...")
    if os.path.exists(os.path.join(workspace_root, "Makefile")):
        commands.append("make test # if target defined")

    if not commands:
        commands.append("Run project test suite and linter")

    return "\n     ".join(commands)

def detect_guidelines(workspace_root):
    guidelines = []
    for name in ["AGENTS.md", "CLAUDE.md", ".cursorrules", "CONTRIBUTING.md", "ENGINEERING_MEMORY.md"]:
        if os.path.exists(os.path.join(workspace_root, name)):
            guidelines.append(f"`{name}`")
    if guidelines:
        return f"Strictly follow project conventions in {', '.join(guidelines)}."
    return "Follow clean architecture, minimal diffs, and existing project conventions."

def extract_modified_files(git_state):
    modified_files = []
    current_repo = None
    in_status_section = False
    in_code_block = False
    for line in git_state.splitlines():
        m = re.match(r"^### Repository: `([^`]+)`", line)
        if m:
            current_repo = m.group(1)
            in_status_section = False
            in_code_block = False
            continue

        if "- **Modified / Untracked Files**:" in line:
            in_status_section = True
            in_code_block = False
            continue
        elif line.startswith("- **") or line.startswith("### "):
            in_status_section = False
            in_code_block = False
            continue

        if in_status_section:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block and current_repo and line.strip():
                line_str = line.strip()
                parts = line_str.split(None, 1)
                if len(parts) >= 2 and any(line_str.startswith(code) for code in ["M ", "A ", "D ", "R ", "C ", "U ", "?? ", "!! ", "MM "]):
                    filepath = parts[1].split(" -> ")[-1].strip()
                    file_rel = f"{current_repo}/{filepath}"
                    if file_rel not in modified_files:
                        modified_files.append(file_rel)
    return modified_files

def generate_handover(workspace_root, task_description="Task transition", outgoing_model="AI Agent", handover_reason="Manual transition / limit reached"):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    git_state = capture_git_state(workspace_root)
    val_commands = detect_validation_commands(workspace_root)
    guidelines = detect_guidelines(workspace_root)
    modified = extract_modified_files(git_state)

    files_section = "\n".join(f"- `{f}`: Modified / staged status" for f in modified) if modified else "- No tracked files in dirty status"

    clean_task = sanitize_secrets(task_description)

    content = f"""# Session Handover Document

> **Handover Notice**: Generated automatically for seamless assistant transition.

---

## 1. Executive Context

- **Original Task**: {clean_task}
- **Outgoing Model**: {outgoing_model}
- **Handover Reason**: {handover_reason}
- **Timestamp**: {now_str}
- **Workspace Root**: `{workspace_root}`

---

## 2. Problem & Behavior Specification

- **Description**: {clean_task}
- **Current Behavior**: Review in-flight workspace state and git diffs below for baseline behavior.
- **Desired Behavior**: Fulfill the requested requirements and test validation.
- **Key Invariants & Scope**: {guidelines}

---

## 3. Current Execution Status

- **Status**: Work in progress / ready for handoff
- **Progress Summary**: In-flight state preserved. See modified files and git diffs below.

---

## 4. What Was Completed

- [x] Initial analysis and workspace state capture completed.

### Files Touched / Modified
{files_section}

---

## 5. In-Flight Workspace State & Git Diffs

{git_state}

---

## 6. Ordered Next Steps (Immediate Action Required)

1. **Step 1 (Immediate)**: Inspect touched files and verify workspace integrity:
   - Run relevant validation commands:
     ```bash
     {val_commands}
     ```
2. **Step 2**: Continue implementation of the original objective:
   - `{clean_task}`
3. **Step 3**: Perform final code quality review and run tests before committing.

---

## 7. Technical Decisions, Invariants & Gotchas

- **Engineering Standards**: {guidelines}
- **Architecture Boundaries**: Keep modular separation and preserve typed contracts.
- **Minimal Diffs**: Make scoped, surgical changes only.

---

## 8. Verification & Testing Status

- **Required Validation**:
  - Run affected test suites.
  - Inspect git diff with minimal diff principle.

---

## 9. Continuation Prompt for Incoming Model

```markdown
You are continuing a task handed over from {outgoing_model}.
Please read `HANDOVER.md` in the project root to understand the full context, in-flight changes, and completed milestones.

Goal:
- Task: {clean_task}

Next Action:
1. Inspect the touched files in `HANDOVER.md`.
2. Run validation tests to confirm baseline integrity.
3. Complete any remaining requirements and run the mandatory final review.

Proceed immediately with reviewing the current state and completing the task.
```
"""
    target = os.path.join(workspace_root, "HANDOVER.md")
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return target

def main():
    workspace_root = os.getcwd()
    task_desc = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Task in progress"
    target = generate_handover(workspace_root, task_description=task_desc)
    print(f"Successfully generated {target}")

if __name__ == "__main__":
    main()
