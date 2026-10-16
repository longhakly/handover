#!/usr/bin/env python3
"""
generate_handover.py

Universal HANDOVER.md generator for all AI coding agents (Claude Code, Gemini, Codex, Cursor).
Can be run:
1. By an agent (Claude, Gemini, Codex) via terminal command.
2. Directly by a developer from the command line:
   python3 scripts/generate_handover.py "Task description"
"""

import argparse
import glob
import json
import os
import re
import shutil
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
    """Masks API keys, tokens, credentials, and private keys thoroughly."""
    if not text:
        return text

    # Mask Private keys
    text = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----", "[REDACTED_PRIVATE_KEY]", text)

    # Mask Bearer tokens / JWTs
    text = re.sub(r"Bearer\s+eyJ[A-Za-z0-9_\-\.]+", "Bearer [REDACTED_JWT]", text)
    text = re.sub(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+", "[REDACTED_JWT]", text)

    # Well-known API key patterns
    text = re.sub(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b", "[REDACTED_API_KEY]", text)
    text = re.sub(r"\bAIza[0-9A-Za-z-_]{35,}\b", "[REDACTED_API_KEY]", text)
    text = re.sub(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b", "[REDACTED_API_KEY]", text)
    text = re.sub(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b", "[REDACTED_AWS_KEY]", text)

    # Key / Secret / Token assignments (quoted or unquoted, e.g. OPENAI_API_KEY=..., token: "...")
    text = re.sub(
        r"(?i)\b([a-z0-9_]*(?:key|secret|token|password|auth|passwd)[a-z0-9_]*)\s*([:=])\s*([\'\"])?([^\s;\'\"]{8,})\3?",
        r"\1\2\3[REDACTED_SECRET]\3",
        text
    )

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

def derive_case_slug(
    task_description: str = "",
    git_state: str = "",
    explicit_case: str = None,
    branches: list = None
) -> str:
    """
    Derives a concise, filesystem-safe case slug according to the following priority:
    1. Explicit case name passed via flag or parameter.
    2. Ticket / Issue key (e.g. PP-2574, ENG-2454) found in task description or active git branch.
    3. Active non-default git branch across workspace repositories.
    4. Task description keywords (kebab-cased, max 50 chars).
    5. Fallback timestamp: session-YYYYMMDD-HHMMSS.
    """
    if explicit_case:
        slug = explicit_case.strip()
        slug = re.sub(r"^HANDOVER[_\-]", "", slug, flags=re.IGNORECASE)
        slug = re.sub(r"\.md$", "", slug, flags=re.IGNORECASE)
        slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", slug).strip("-")
        if slug:
            return slug

    ticket_pattern = r"\b([A-Z]{2,10}-\d+)\b"

    # Priority 2: Ticket / Issue key regex in task description
    if task_description:
        ticket_match = re.search(ticket_pattern, task_description)
        if ticket_match:
            ticket = ticket_match.group(1).upper()
            remainder = task_description[:ticket_match.start()] + " " + task_description[ticket_match.end():]
            words = re.findall(r"[a-zA-Z0-9]+", remainder)
            noise = {"fix", "bug", "feature", "task", "issue", "the", "a", "an", "and", "or", "to", "in", "for", "on", "with"}
            context_words = [w.lower() for w in words if w.lower() not in noise]
            suffix = "-".join(context_words[:4])
            return f"{ticket}-{suffix}" if suffix else ticket

    # Extract branches from git_state or parameter
    detected_branches = list(branches) if branches else []
    if git_state:
        branch_matches = re.findall(r"- \*\*Branch\*\*: `([^`()]+)`", git_state)
        for b in branch_matches:
            b_clean = b.strip().split()[0]
            if b_clean not in detected_branches:
                detected_branches.append(b_clean)

    ignored_branches = {"main", "master", "dev", "develop", "staging", "head", "unknown"}
    active_branches = [
        b for b in detected_branches
        if b.lower() not in ignored_branches and not b.startswith("HEAD")
    ]

    for b in active_branches:
        b_clean = re.sub(r"^(?:feature|bugfix|hotfix|chore|refactor|test)/", "", b, flags=re.IGNORECASE)
        b_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", b_clean).strip("-")
        if b_slug:
            return b_slug[:50].rstrip("-")

    # Priority 4: Task description keywords
    if task_description:
        clean_desc = task_description.strip()
        generic_phrases = {"task transition", "task in progress", "manual transition", "session handover", "handover"}
        if clean_desc.lower() not in generic_phrases:
            words = re.findall(r"[a-zA-Z0-9]+", clean_desc)
            if words:
                slug = "-".join(w.lower() for w in words[:6])
                slug = slug[:50].rstrip("-")
                if slug:
                    return slug

    # Priority 5: Fallback timestamp
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"session-{now_str}"

def generate_handover(
    workspace_root,
    task_description="Task transition",
    outgoing_model="AI Agent",
    handover_reason="Manual transition / limit reached",
    explicit_case=None,
    output_dir=None,
    update_root_pointer=True,
):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    git_state = capture_git_state(workspace_root)
    val_commands = detect_validation_commands(workspace_root)
    guidelines = detect_guidelines(workspace_root)
    modified = extract_modified_files(git_state)

    files_section = "\n".join(f"- `{f}`: Modified / staged status" for f in modified) if modified else "- No tracked files in dirty status"

    clean_task = sanitize_secrets(task_description)
    case_slug = derive_case_slug(task_description=clean_task, git_state=git_state, explicit_case=explicit_case)
    case_filename = f"HANDOVER_{case_slug}.md"

    content = f"""# Session Handover Document

> **Handover Notice**: Generated automatically for seamless assistant transition.

---

## 1. Executive Context

- **Original Task**: {clean_task}
- **Case Identifier**: `{case_slug}`
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
Please read `{case_filename}` in the project root to understand the full context, in-flight changes, and completed milestones.

Goal:
- Task: {clean_task}
- Case Identifier: {case_slug}

Next Action:
1. Inspect the touched files in `{case_filename}`.
2. Run validation tests to confirm baseline integrity.
3. Complete any remaining requirements and run the mandatory final review.

Proceed immediately with reviewing the current state and completing the task.
```
"""
    target_dir = output_dir if output_dir else workspace_root
    target = os.path.join(target_dir, case_filename)

    if os.path.exists(target):
        backup_path = f"{target}.bak"
        try:
            shutil.copy2(target, backup_path)
            print(f"Backed up existing {target} to {backup_path}")
        except Exception as e:
            print(f"Warning: Failed to create backup: {e}", file=sys.stderr)

    with open(target, "w", encoding="utf-8") as f:
        f.write(sanitize_secrets(content))

    root_pointer = os.path.join(workspace_root, "HANDOVER.md")
    if update_root_pointer and os.path.abspath(target) != os.path.abspath(root_pointer):
        try:
            if os.path.exists(root_pointer):
                backup_pointer = f"{root_pointer}.bak"
                shutil.copy2(root_pointer, backup_pointer)
            shutil.copy2(target, root_pointer)
        except Exception as e:
            print(f"Warning: Failed to update root HANDOVER.md: {e}", file=sys.stderr)

    return target

def main():
    parser = argparse.ArgumentParser(description="Universal case-specific HANDOVER generator.")
    parser.add_argument("task", nargs="*", default=[], help="Task description or objective")
    parser.add_argument("--case", "-c", dest="case_name", default=None, help="Explicit case name (e.g. PP-2574-fix)")
    parser.add_argument("--output-dir", "-d", dest="output_dir", default=None, help="Directory to save handover file")
    args = parser.parse_args()

    workspace_root = os.getcwd()
    task_desc = " ".join(args.task) if args.task else "Task in progress"
    target = generate_handover(
        workspace_root,
        task_description=task_desc,
        explicit_case=args.case_name,
        output_dir=args.output_dir
    )
    print(f"Successfully generated {target}")
    root_pointer = os.path.join(workspace_root, "HANDOVER.md")
    if os.path.abspath(target) != os.path.abspath(root_pointer):
        print(f"Updated latest pointer: {root_pointer}")

if __name__ == "__main__":
    main()
