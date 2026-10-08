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

# Run background recovery check without blocking Codex UI
python3 -c "
import glob, json, os, subprocess, sys

sessions = glob.glob(os.path.expanduser('~/.codex/sessions/**/*.jsonl'), recursive=True)
if not sessions:
    sys.exit(0)
sessions.sort(key=os.path.getmtime)
latest_session = sessions[-1]

try:
    with open(latest_session, 'rb') as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - 32768))
        tail = f.read().decode('utf-8', errors='replace')

    # Trigger if hard error occurred or rate limit usage exceeded 95%
    if 'usage_limit_exceeded' in tail or any(f'\"used_percent\": {p}' in tail for p in range(95, 101)):
        cwd = os.getcwd()
        # Find recover_last_codex_session.py dynamically
        candidates = [
            os.path.join(cwd, '.agents/skills/handover/scripts/recover_last_codex_session.py'),
            os.path.join(cwd, 'scripts/recover_last_codex_session.py'),
            os.path.expanduser('~/.agents/skills/handover/scripts/recover_last_codex_session.py'),
        ]
        script = next((c for c in candidates if os.path.exists(c)), None)
        if script:
            subprocess.run([sys.executable, script, latest_session], cwd=cwd)
except Exception:
    pass
" &
