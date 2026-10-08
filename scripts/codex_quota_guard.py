#!/usr/bin/env python3
"""
codex_quota_guard.py

PreToolUse hook for OpenAI Codex CLI.
Monitors rate limits and token quotas from the active Codex session log.
When remaining limit drops below 5% (usage >= 95%):
1. Automatically triggers recover_last_codex_session.py to generate HANDOVER.md.
2. Emits an emergency stop alert to stderr.
3. Exits with status 2 to block the tool call and halt execution cleanly before API rejection.
"""

import glob
import json
import os
import subprocess
import sys

THRESHOLD_PERCENT = 95.0

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
    if not session_path or not os.path.exists(session_path):
        return None

    try:
        with open(session_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            # Read last 64KB for recent events
            read_size = min(size, 65536)
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

def main():
    transcript_path = None
    cwd = os.getcwd()

    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                hook_input = json.loads(stdin_data)
                transcript_path = hook_input.get("transcript_path") or hook_input.get("session_path")
                cwd = hook_input.get("cwd", cwd)
        except Exception:
            pass

    if not transcript_path or not os.path.exists(transcript_path):
        transcript_path = find_latest_session(cwd)

    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

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

    if used_percent is not None and used_percent >= THRESHOLD_PERCENT:
        # < 5% threshold reached! Trigger Emergency Handover!
        recovery_script = find_recovery_script(cwd)
        if recovery_script:
            subprocess.run([sys.executable, recovery_script, transcript_path], cwd=cwd, timeout=10)

        sys.stderr.write(
            f"\n[EMERGENCY HANDOVER TRIGGERED - REMAINING LIMIT < 5%]\n"
            f"Current rate limit usage: {used_percent}% (threshold: {THRESHOLD_PERCENT}%).\n"
            f"Execution halted cleanly to preserve workspace integrity and avoid mid-edit termination.\n"
            f"HANDOVER.md has been automatically generated at: {cwd}/HANDOVER.md\n"
            f"Switch to Gemini, Claude, or another assistant to resume seamlessly.\n"
        )
        sys.exit(2)

    sys.exit(0)

if __name__ == "__main__":
    main()
