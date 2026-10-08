#!/usr/bin/env bash
# notify_handover_guard.sh
# Universal turn-ended notification hook for OpenAI Codex CLI.
# Add to ~/.codex/config.toml:
# notify = ["/path/to/notify_handover_guard.sh", "turn-ended"]

# If using SkyComputerUseClient or desktop app, preserve notification chaining
SKY_CLIENT="$HOME/.codex/computer-use/Codex Computer Use.app/Contents/SharedSupport/SkyComputerUseClient.app/Contents/MacOS/SkyComputerUseClient"
if [ -f "$SKY_CLIENT" ]; then
    "$SKY_CLIENT" "$@" &
fi

# Run synchronous recovery check with timeout so Codex does not exit before writing HANDOVER.md
python3 -c '
import glob, json, os, re, subprocess, sys

# 1. Parse hook stdin if available
transcript_path = None
target_cwd = os.path.realpath(os.getcwd())

if not sys.stdin.isatty():
    try:
        raw_input = sys.stdin.read().strip()
        if raw_input:
            hook_data = json.loads(raw_input)
            transcript_path = hook_data.get("transcript_path") or hook_data.get("session_path")
            if "cwd" in hook_data:
                target_cwd = os.path.realpath(hook_data["cwd"])
    except Exception:
        pass

# 2. Find latest session belonging to target_cwd (avoid cross-project contamination)
if not transcript_path or not os.path.exists(transcript_path):
    sessions = glob.glob(os.path.expanduser("~/.codex/sessions/**/*.jsonl"), recursive=True)
    if not sessions:
        sys.exit(0)
    sessions.sort(key=os.path.getmtime, reverse=True)

    def matches_cwd(spath, cwd):
        try:
            with open(spath, "r", encoding="utf-8", errors="replace") as f:
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
                    if data.get("cwd") and os.path.realpath(data["cwd"]) == cwd:
                        return True
                    p = data.get("payload")
                    if isinstance(p, dict):
                        if p.get("cwd") and os.path.realpath(p["cwd"]) == cwd:
                            return True
                        for r in p.get("workspace_roots", []):
                            if os.path.realpath(r) == cwd:
                                return True
        except Exception:
            pass
        return False

    latest_session = next((s for s in sessions if matches_cwd(s, target_cwd)), None)
else:
    latest_session = transcript_path

if not latest_session or not os.path.exists(latest_session):
    sys.exit(0)

try:
    with open(latest_session, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 32768))
        tail = f.read().decode("utf-8", errors="replace")

    limit_exceeded = "usage_limit_exceeded" in tail
    used_pct = None
    pct_match = re.search(r"\"used_percent\"\s*:\s*(\d+(?:\.\d+)?)", tail)
    if pct_match:
        try:
            used_pct = float(pct_match.group(1))
        except ValueError:
            pass

    # Trigger if hard error occurred or rate limit usage exceeded 95%
    if limit_exceeded or (used_pct is not None and used_pct >= 95.0):
        candidates = [
            os.path.join(target_cwd, ".agents/skills/handover/scripts/recover_last_codex_session.py"),
            os.path.join(target_cwd, "scripts/recover_last_codex_session.py"),
            os.path.expanduser("~/.agents/skills/handover/scripts/recover_last_codex_session.py"),
        ]
        script = next((c for c in candidates if os.path.exists(c)), None)
        if script:
            subprocess.run([sys.executable, script, latest_session], cwd=target_cwd, timeout=10)
except Exception:
    pass
'
