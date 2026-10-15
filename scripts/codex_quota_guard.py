#!/usr/bin/env python3
"""
codex_quota_guard.py

PreToolUse hook for OpenAI Codex CLI.
Monitors rate limits and token quotas from the active Codex session log.
When remaining limit drops below 2% (usage >= 98%):
1. Automatically triggers recover_last_codex_session.py to generate HANDOVER.md (once per halt state).
2. Emits an emergency stop alert to stderr.
3. Exits with status 2 to block work tool calls and halt execution cleanly before API rejection.
4. Allows exact read-only diagnostic control calls (e.g. get_usage_limits) so live account quota
   can be queried and refreshed without being denied by stale transcript snapshots.
"""

import glob
import json
import os
import re
import subprocess
import sys
import time

THRESHOLD_PERCENT = 98.0

# Disallowed tokens inside wrapped exec calls
DISALLOWED_EXEC_PATTERNS = [
    r"\bexec_command\b", r"\brun_command\b", r"\bspawn\b", r"\bsubprocess\b",
    r"\bbash\b", r"\bsh\b", r"\bzsh\b", r"\bpowershell\b", r"\bcurl\b", r"\bwget\b",
    r"\breadFile\b", r"\bwriteFile\b", r"\beditFile\b", r"\bpatchFile\b",
    r"\bcreateFile\b", r"\bappendFile\b", r"\bfs\.", r"\bopen\s*\(",
    r"\bunlink\b", r"\brename\b", r"\bmkdir\b", r"\brm\s+",
    r"\bsendMessage\b", r"\bsend_message\b", r"\binvoke_subagent\b",
    r"\bsubagent\b", r"\bdispatch\b",
    r"\bgit\s+", r"\bgit\b", r"\bworktree\b",
]

# Exact read-only control queries allowed when wrapped in exec
ALLOWED_EXEC_CONTROL_REGEX = re.compile(
    r"^(?:(?:const|let|var)\s+\w+\s*=\s*)?(?:return\s+)?(?:await\s+)?(?:tools\.)?(?:get_usage_limits|getUsageLimits|get_rate_limits)\s*\(\s*\)\s*;?$",
    re.IGNORECASE
)

def is_diagnostic_control_call(tool_name: str, tool_input: object) -> bool:
    """
    Identifies narrowly recognized read-only diagnostic / control-plane calls.
    Allows agents to query active account quota even during a quota halt.
    Rejects any mixed payloads containing shell, file, messaging, or worktree operations.
    """
    if not tool_name or not isinstance(tool_name, str):
        return False

    name = tool_name.strip().lower()

    # 1. Direct diagnostic tool calls
    if name in ("get_usage_limits", "getusagelimits", "get_rate_limits", "getratelimits", "usage_limits"):
        if isinstance(tool_input, dict):
            keys = [k.lower() for k in tool_input.keys()]
            if any(k in keys for k in ("cmd", "command", "file", "path", "patch", "script", "code")):
                return False
        return True

    # 2. Control call wrapped in exec / evaluate
    if name in ("exec", "execute", "eval", "code_mode"):
        code = ""
        if isinstance(tool_input, dict):
            code = tool_input.get("code") or tool_input.get("cmd") or tool_input.get("script") or ""
        elif isinstance(tool_input, str):
            code = tool_input

        if not isinstance(code, str) or not code.strip():
            return False

        code_str = code.strip()

        # Reject any disallowed shell, file, messaging, or worktree operations
        for pattern in DISALLOWED_EXEC_PATTERNS:
            if re.search(pattern, code_str, re.IGNORECASE):
                return False

        # Allow only exact control call
        if ALLOWED_EXEC_CONTROL_REGEX.match(code_str):
            return True

    return False

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

def find_latest_session(target_cwd: str = None) -> str:
    """Finds the newest session log, filtering by workspace cwd to prevent cross-project leaks."""
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

def get_latest_rate_limits(session_path: str):
    """
    Reads the latest rate_limits event from the tail of the session log.
    Efficiently seeks to the tail (last 256KB) to avoid reading massive files.
    """
    if not session_path or not os.path.exists(session_path):
        return None

    try:
        with open(session_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            # Read last 256KB for recent events
            read_size = min(size, 262144)
            f.seek(size - read_size)
            lines = f.read().decode("utf-8", errors="replace").splitlines()

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue

            payload = data.get("payload", {})
            if data.get("type") == "event_msg" and payload.get("type") == "token_count":
                rl = payload.get("rate_limits")
                if rl:
                    return rl
    except Exception:
        pass
    return None

def find_recovery_script(cwd: str) -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "recover_last_codex_session.py"),
        os.path.join(cwd, ".agents/skills/handover/scripts/recover_last_codex_session.py"),
        os.path.join(cwd, "scripts/recover_last_codex_session.py"),
        os.path.expanduser("~/.agents/skills/handover/scripts/recover_last_codex_session.py"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None

def is_handover_already_generated(cwd: str, transcript_path: str, used_percent: float) -> bool:
    """
    Checks if a handover document has already been generated for the active session halt state.
    Prevents repeated recovery spawns and backup thrashing on consecutive blocked calls.
    """
    handover_path = os.path.join(cwd, "HANDOVER.md")
    if not os.path.exists(handover_path):
        return False

    state_marker = os.path.join(cwd, ".agents/skills/handover/.last_handover_halt.json")
    if os.path.exists(state_marker):
        try:
            with open(state_marker, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("transcript_path") == transcript_path and abs(state.get("used_percent", 0.0) - used_percent) < 0.1:
                return True
        except Exception:
            pass

    # Fallback: if HANDOVER.md exists and was modified within the last 120 seconds for the same session
    try:
        mtime = os.path.getmtime(handover_path)
        if (time.time() - mtime) < 120:
            with open(handover_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(2048)
                if f"{used_percent}%" in content:
                    return True
    except Exception:
        pass

    return False

def record_handover_generated(cwd: str, transcript_path: str, used_percent: float):
    """Records that handover generation completed for this halt state."""
    state_dir = os.path.join(cwd, ".agents/skills/handover")
    if not os.path.exists(state_dir):
        return
    state_marker = os.path.join(state_dir, ".last_handover_halt.json")
    try:
        with open(state_marker, "w", encoding="utf-8") as f:
            json.dump({
                "transcript_path": transcript_path,
                "used_percent": used_percent,
                "timestamp": time.time(),
            }, f)
    except Exception:
        pass

def main():
    transcript_path = None
    cwd = os.getcwd()
    tool_name = None
    tool_input = None

    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                hook_input = json.loads(stdin_data)
                transcript_path = hook_input.get("transcript_path") or hook_input.get("session_path")
                cwd = hook_input.get("cwd", cwd)
                tool_name = hook_input.get("tool_name") or hook_input.get("name")
                tool_input = hook_input.get("tool_input") if "tool_input" in hook_input else hook_input.get("input")
                if tool_input is None:
                    tool_input = hook_input.get("arguments") or hook_input.get("parameters")
        except Exception:
            pass

    # 1. Narrowly recognized read-only diagnostic control calls are ALWAYS allowed
    if is_diagnostic_control_call(tool_name, tool_input):
        sys.exit(0)

    # 2. Locate active session transcript
    if not transcript_path or not os.path.exists(transcript_path):
        transcript_path = find_latest_session(cwd)

    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    # 3. Check rate limits from transcript tail
    rate_limits = get_latest_rate_limits(transcript_path)
    if not rate_limits:
        sys.exit(0)

    primary = rate_limits.get("primary") or {}
    raw_used = primary.get("used_percent")
    used_percent = None
    if raw_used is not None:
        try:
            used_percent = float(raw_used)
        except (ValueError, TypeError):
            pass

    # Also inspect secondary limit if present
    secondary = rate_limits.get("secondary") or {}
    raw_sec = secondary.get("used_percent")
    if raw_sec is not None:
        try:
            sec_used = float(raw_sec)
            if used_percent is None or sec_used > used_percent:
                used_percent = sec_used
        except (ValueError, TypeError):
            pass

    if used_percent is not None and used_percent >= THRESHOLD_PERCENT:
        # Halt work tools: remaining limit < 2% (threshold: 98.0%)
        # Only generate handover once per halt state to avoid disk thrashing
        if not is_handover_already_generated(cwd, transcript_path, used_percent):
            recovery_script = find_recovery_script(cwd)
            if recovery_script:
                subprocess.run([sys.executable, recovery_script, transcript_path], cwd=cwd, timeout=10)
                record_handover_generated(cwd, transcript_path, used_percent)

        sys.stderr.write(
            f"\n[EMERGENCY HANDOVER TRIGGERED - REMAINING LIMIT < 2%]\n"
            f"Current rate limit usage: {used_percent}% (threshold: {THRESHOLD_PERCENT}%).\n"
            f"Execution halted cleanly to preserve workspace integrity and avoid mid-edit termination.\n"
            f"HANDOVER.md is available at: {cwd}/HANDOVER.md\n"
            f"DIAGNOSTIC NOTICE: Read-only `get_usage_limits` (or `tools.get_usage_limits()`) is permitted.\n"
            f"If account quota was reset or refreshed, run `get_usage_limits` to append a fresh snapshot before resuming work tools.\n"
        )
        sys.exit(2)

    sys.exit(0)

if __name__ == "__main__":
    main()
