#!/usr/bin/env python3
"""
recover_last_codex_session.py

Reconstructs and generates a comprehensive, production-ready HANDOVER.md from local
OpenAI Codex session logs (~/.codex/sessions/**/*.jsonl) and active git state.

Works both:
1. Automatically when triggered by quota guard hooks upon reaching < 5% limits.
2. Post-mortem after Codex process crashes, rate limits (HTTP 429), or abrupt exits.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

def session_matches_cwd(session_path: str, target_cwd: str) -> bool:
    """Verifies that a session log belongs to the specified workspace directory."""
    target_cwd = os.path.realpath(target_cwd)
    try:
        with open(session_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 50:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if data.get("cwd") and os.path.realpath(data["cwd"]) == target_cwd:
                    return True
                payload = data.get("payload")
                if isinstance(payload, dict):
                    if payload.get("cwd") and os.path.realpath(payload["cwd"]) == target_cwd:
                        return True
                    roots = payload.get("workspace_roots", [])
                    if isinstance(roots, list):
                        for r in roots:
                            if os.path.realpath(r) == target_cwd:
                                return True
    except Exception:
        pass
    return False

def find_latest_codex_session(target_cwd: str = None) -> str:
    """Finds the latest Codex session log, filtering by workspace cwd to prevent cross-project leaks."""
    sessions_pattern = os.path.expanduser("~/.codex/sessions/**/*.jsonl")
    files = glob.glob(sessions_pattern, recursive=True)
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    if target_cwd:
        for f in files:
            if session_matches_cwd(f, target_cwd):
                return f
        return None
    return files[0]

def extract_session_details(session_path):
    user_requests = []
    agent_messages = []
    tool_actions = []
    last_error = None
    last_rate_limits = None
    model_name = "Codex"
    created_at = None

    with open(session_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue

            t = data.get("type")
            payload = data.get("payload", {})
            ts = data.get("timestamp")
            if ts and not created_at:
                created_at = ts

            # Model metadata
            if "model" in data:
                model_name = data["model"]
            if isinstance(payload, dict) and "model" in payload:
                model_name = payload["model"]

            # Event messages
            if t == "event_msg":
                msg_type = payload.get("type")
                if msg_type == "task_complete" and payload.get("error"):
                    last_error = payload.get("error")
                elif msg_type == "token_count" and payload.get("rate_limits"):
                    last_rate_limits = payload.get("rate_limits")
                elif msg_type == "agent_message":
                    msg = payload.get("message")
                    if msg:
                        agent_messages.append(msg)

            # User prompts
            elif t == "response_item" and payload.get("role") == "user":
                for item in payload.get("content", []):
                    if item.get("type") == "input_text":
                        txt = item.get("text", "")
                        # Filter out system boilerplate
                        if (
                            txt
                            and not txt.startswith("# AGENTS.md")
                            and not txt.startswith("<environment_context")
                            and not txt.startswith("<external_codex")
                        ):
                            user_requests.append(txt)

            # Tool calls
            elif t == "response_item" and payload.get("type") == "custom_tool_call":
                name = payload.get("name", "")
                inp = payload.get("input", "")
                tool_actions.append({"name": name, "input": inp})

    return {
        "path": session_path,
        "created_at": created_at,
        "model_name": model_name,
        "user_requests": user_requests,
        "agent_messages": agent_messages,
        "tool_actions": tool_actions,
        "last_error": last_error,
        "last_rate_limits": last_rate_limits,
    }

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

def parse_user_goal(user_requests):
    if not user_requests:
        return "Unknown task"

    clean_prompts = []
    for req in user_requests:
        cleaned = re.sub(r"# Context from my IDE setup:.*?(## My request:\s*|\Z)", "", req, flags=re.DOTALL).strip()
        if cleaned:
            clean_prompts.append(sanitize_secrets(cleaned))
        elif "## My request:" in req:
            extracted = req.split("## My request:")[-1].strip()
            if extracted:
                clean_prompts.append(sanitize_secrets(extracted))

    if clean_prompts:
        return clean_prompts[0]
    return sanitize_secrets(user_requests[-1][:300])

def parse_problem_specification(user_requests, last_error=None):
    raw_prompt = parse_user_goal(user_requests)

    description = raw_prompt
    current_behavior = "Baseline system state prior to changes."
    desired_behavior = "Fulfill the requested task and changes according to specification."

    curr_match = re.search(
        r"(?:current\s*behavior|currently|problem|issue):\s*(.*?)(?=(?:desired\s*behavior|expected|should|goal|\n\n|\Z))",
        raw_prompt,
        re.IGNORECASE | re.DOTALL,
    )
    if curr_match and curr_match.group(1).strip():
        current_behavior = curr_match.group(1).strip()
    elif last_error:
        err_msg = last_error.get("message", "")
        err_code = last_error.get("codex_error_info", "")
        current_behavior = f"Encountered error/halt during execution ({err_code}: {err_msg})" if err_code else err_msg
    elif "got this issue" in raw_prompt.lower() or "error" in raw_prompt.lower() or "issue" in raw_prompt.lower():
        if "help" in raw_prompt.lower():
            current_behavior = f"Reported issue in existing tool/environment: {raw_prompt.split('help')[0].strip()}"
        else:
            current_behavior = f"Reported issue in existing tool/environment: {raw_prompt[:250]}"

    des_match = re.search(
        r"(?:desired\s*behavior|desired|expected\s*behavior|expected|goal):\s*(.*?)(?=(?:current|\n\n|\Z))",
        raw_prompt,
        re.IGNORECASE | re.DOTALL,
    )
    if des_match and des_match.group(1).strip():
        desired_behavior = des_match.group(1).strip()
    else:
        for kw in ["help ", "please ", "need to ", "should ", "fix ", "want to ", "clone ", "implement "]:
            lower_p = raw_prompt.lower()
            if kw in lower_p:
                idx = lower_p.find(kw)
                extracted = raw_prompt[idx:].strip()
                if extracted:
                    desired_behavior = extracted[0].upper() + extracted[1:]
                    break

    return {
        "description": sanitize_secrets(description),
        "current_behavior": sanitize_secrets(current_behavior),
        "desired_behavior": sanitize_secrets(desired_behavior),
    }

def determine_handover_reason(last_error, rate_limits):
    if last_error:
        code = last_error.get("codex_error_info", "")
        msg = last_error.get("message", "")
        if code == "usage_limit_exceeded" or "usage limit" in msg.lower():
            return f"Codex usage limit exhausted (API 429 usage_limit_exceeded: {msg})"
        return f"Codex execution error ({code}: {msg})"

    if rate_limits:
        primary = rate_limits.get("primary") or {}
        used = primary.get("used_percent")
        if used is not None and used >= 95.0:
            return f"Remaining quota dropped below 5% threshold (Rate limit usage: {used}%)"

    return "Session transition / limits approaching threshold"

def detect_validation_commands(workspace_root):
    commands = []
    # Node / TypeScript / JavaScript
    if os.path.exists(os.path.join(workspace_root, "package.json")):
        commands.append("npm test # or pnpm test / yarn test / bun test")
        commands.append("npm run build # or typecheck")
    # Python
    if any(os.path.exists(os.path.join(workspace_root, f)) for f in ["pyproject.toml", "requirements.txt", "Pipfile", "setup.py"]):
        commands.append("pytest")
        if os.path.exists(os.path.join(workspace_root, "pyproject.toml")):
            commands.append("ruff check # or flake8 / mypy")
    # Rust
    if os.path.exists(os.path.join(workspace_root, "Cargo.toml")):
        commands.append("cargo test")
        commands.append("cargo check")
    # Go
    if os.path.exists(os.path.join(workspace_root, "go.mod")):
        commands.append("go test ./...")
    # Makefile
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

def generate_handover_content(workspace_root, details):
    user_goal = parse_user_goal(details["user_requests"])
    problem_spec = parse_problem_specification(details["user_requests"], details.get("last_error"))
    handover_reason = determine_handover_reason(details["last_error"], details["last_rate_limits"])
    model_name = details["model_name"]
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    git_state = capture_git_state(workspace_root)
    val_commands = detect_validation_commands(workspace_root)
    guideline_rules = detect_guidelines(workspace_root)

    # Analyze agent messages to determine stage and completed work (with secret scrubbing)
    agent_msgs = details["agent_messages"]
    completed_bullets = []
    latest_summary = "Task was interrupted during execution."

    if agent_msgs:
        latest_summary = sanitize_secrets(agent_msgs[-1].strip())
        for msg in agent_msgs:
            if "Phase A" in msg or "plan" in msg.lower():
                completed_bullets.append("Completed task analysis and plan formulation.")
            elif "verification passed" in msg.lower() or "verified" in msg.lower():
                first_line = msg.split("\n")[0]
                completed_bullets.append(sanitize_secrets(first_line[:150]))
            elif "implemented" in msg.lower():
                first_line = msg.split("\n")[0]
                completed_bullets.append(sanitize_secrets(first_line[:150]))

    if not completed_bullets and agent_msgs:
        completed_bullets = [sanitize_secrets(agent_msgs[0][:150])]

    # Extract touched files cleanly from status blocks, ignoring diffstat blocks
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

    completed_str = "\n".join([f"- {b}" for b in completed_bullets]) if completed_bullets else "- Initial review of requirements."
    modified_str = "\n".join([f"- `{f}`" for f in modified_files]) if modified_files else "- None detected."

    # Immediate next steps
    next_steps = []
    if modified_files:
        next_steps.append(f"Review uncommitted changes in: {', '.join([f'`{f}`' for f in modified_files[:3]])}.")
    next_steps.append("Run project test suite and verification commands.")
    next_steps.append("Complete any remaining requirements and run the mandatory final review.")
    next_steps_str = "\n".join([f"{i+1}. {step}" for i, step in enumerate(next_steps)])

    handover_md = f"""# Session Handover Document

## 1. Executive Context

- **Task**: {user_goal}
- **Outgoing Model / Environment**: {model_name}
- **Handover Trigger / Reason**: {handover_reason}
- **Timestamp**: {now_str}
- **Workspace Root**: `{workspace_root}`

---

## 2. Problem & Behavior Specification

- **Description**:
  {problem_spec["description"]}
- **Current Behavior**:
  {problem_spec["current_behavior"]}
- **Desired Behavior**:
  {problem_spec["desired_behavior"]}
- **Key Invariants & Scope**:
  - Keep changes cohesive, scoped, and minimal.
  - Adhere to existing coding style and architecture boundaries.

---

## 3. Current Execution Status

- **Status**: Interrupted / Handover in progress
- **Latest Summary from Outgoing Model**:
  > {latest_summary}

---

## 4. What Was Completed

### Finished Milestones
{completed_str}

### Touched & Modified Files
{modified_str}

---

## 5. In-Flight Workspace State & Git Diffs

{git_state}

---

## 6. Ordered Next Steps (Immediate Action Required)

{next_steps_str}

**Validation Commands**:
```bash
{val_commands}
```

---

## 7. Technical Decisions, Invariants & Gotchas

- **Engineering Standards**: {guideline_rules}
- **Architecture Boundaries**: Keep modular separation, preserve typed schemas, and avoid tight coupling.
- **Minimal Diffs**: Make surgical, scoped edits only; do not refactor unrelated code.

---

## 8. Verification & Testing Status

- **Previous Verification**:
  > {latest_summary}
- **Required Validation**:
  - Run affected test suites.
  - Inspect git diff with minimal diff principle.

---

## 9. Continuation Prompt for Incoming Model

```markdown
You are continuing a task handed over from {model_name}.
Please read `HANDOVER.md` in the project root to understand the full context, in-flight changes, and completed milestones.

Goal:
- Task: {user_goal}
- Outgoing state: {latest_summary}

Next Action:
1. Inspect the touched files in `HANDOVER.md`.
2. Run validation tests to confirm baseline integrity.
3. Complete any remaining requirements and run the mandatory final review.

Proceed immediately with reviewing the current state and completing the task.
```
"""
    return sanitize_secrets(handover_md)

def main():
    workspace_root = os.getcwd()
    session_file = None

    if len(sys.argv) > 1:
        session_file = sys.argv[1]
    elif not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                hook_input = json.loads(stdin_data)
                session_file = hook_input.get("transcript_path") or hook_input.get("session_path")
                if "cwd" in hook_input:
                    workspace_root = hook_input["cwd"]
        except Exception:
            pass

    if not session_file:
        session_file = find_latest_codex_session(workspace_root)

    if not session_file or not os.path.exists(session_file):
        print(f"Error: No valid Codex session log found for workspace: {workspace_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting session from: {session_file}")
    details = extract_session_details(session_file)
    print(f"Model: {details['model_name']}")
    if details['last_error']:
        print(f"Last error: {details['last_error'].get('codex_error_info')} - {details['last_error'].get('message')}")

    handover_text = generate_handover_content(workspace_root, details)

    target_handover_path = os.path.join(workspace_root, "HANDOVER.md")
    if os.path.exists(target_handover_path):
        backup_path = f"{target_handover_path}.bak"
        try:
            shutil.copy2(target_handover_path, backup_path)
            print(f"Backed up existing {target_handover_path} to {backup_path}")
        except Exception as e:
            print(f"Warning: Failed to create backup: {e}", file=sys.stderr)

    with open(target_handover_path, "w", encoding="utf-8") as f:
        f.write(handover_text)

    print(f"Successfully generated {target_handover_path}")

if __name__ == "__main__":
    main()
