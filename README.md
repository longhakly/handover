# Handover (`HANDOVER.md`)

> **Zero-loss context handovers and automated quota protection for AI coding agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Supported Agents](https://img.shields.io/badge/Agents-Codex%20%7C%20Gemini%20%7C%20Claude%20%7C%20Antigravity-orange.svg)](#supported-ecosystem)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-green.svg)](#installation)

**Handover** is a portable skill and automation framework that solves the two biggest pain points of working with autonomous AI coding agents:
1. **The 5% Token & Rate-Limit Cliff**: Agents running out of tokens or hitting API rate limits (HTTP 429) mid-turn, leaving broken syntax, dirty git states, and lost context.
2. **Cross-Model Switching Friction**: Having to manually re-explain task status, completed milestones, and immediate next steps when switching between assistants (e.g., **OpenAI Codex** $\leftrightarrow$ **Google Gemini** $\leftrightarrow$ **Anthropic Claude**).

Whenever session limits approach exhaustion—or whenever you type `"handover"` in chat—this skill immediately captures workspace state, redacts secrets, and generates a structured, production-ready `HANDOVER.md` in your project root with a copy-pasteable continuation prompt.

---

## ⚡ Key Features

* 🛡️ **Automated `< 5%` Emergency Quota Guard**: Halts tool execution at 95% rate-limit usage, preventing unexpected `usage_limit_exceeded` / HTTP 429 cutoffs midway through editing files.
* 📋 **Structured `HANDOVER.md`**: Persists a complete specification breakdown: **Problem Description**, **Current Behavior**, **Desired Behavior**, **Milestones**, **Uncommitted Work**, and **Ordered Next Steps**.
* 🔄 **Zero-Loss Model Transitions**: Move smoothly between models (Codex $\leftrightarrow$ Gemini $\leftrightarrow$ Claude $\leftrightarrow$ Cursor) with a single copy-paste prompt.
* 🔒 **Automatic Secret Redaction**: Built-in sanitization redacts Bearer tokens, JWTs, and API keys so credentials never leak into markdown or git history.
* 🚀 **Smart Stack Auto-Detection**: Auto-detects project testing and build commands across **Node.js / TypeScript**, **Python**, **Rust**, **Go**, and **Makefiles**.
* 🧹 **Clean Git Parsing**: Isolates modified and untracked files cleanly from `git status` without polluting reports with diffstat markers (`+++++`, `deletions(-)`).
* 🗂️ **Multi-Repo Workspace Support**: Recursively inspects and reports dirty state across mono-repos and multi-repository project roots.
* 🩹 **Post-Mortem Session Recovery**: Reconstructs complete context from local JSONL logs even after an agent process crashes or exits abruptly.

---

## 📄 Structure of `HANDOVER.md`

Every handover generates a standardized, single-file context ledger:

```markdown
# Session Handover Document

## 1. Executive Context
- Task, outgoing model, handover reason, timestamp, branch.

## 2. Problem & Behavior Specification
- **Description**: What is being built or solved.
- **Current Behavior**: Existing baseline, broken behavior, or error logs.
- **Desired Behavior**: Target outcome and acceptance criteria.
- **Key Invariants & Scope**: Project rules and architectural boundaries.

## 3. Current Execution Status
- Plan phase and real-time execution summary.

## 4. What Was Completed
- Checklist of finished items and touched files.

## 5. In-Flight Workspace State & Git Diffs
- Auto-captured git branches, status, and staged/unstaged diffs.

## 6. Ordered Next Steps (Immediate Action Required)
- Numbered action items with exact target files and functions to edit.

## 7. Technical Decisions, Invariants & Gotchas
- Architecture patterns and constraints that must be preserved.

## 8. Verification & Testing Status
- Passing vs pending validation commands (`npm test`, `pytest`, etc.).

## 9. Continuation Prompt for Incoming Model
- Ready-to-use prompt formatted for the receiving model to resume immediately.
```

---

## 📦 Installation

### Option 1: Install in a Specific Project (Recommended)

Clone or copy this repository into your project's `.agents/skills/handover` directory:

```bash
# From your project root:
mkdir -p .agents/skills
git clone https://github.com/longhakly/handover.git .agents/skills/handover
```

### Option 2: Install Globally for All Projects

Clone into your user-level skills directory:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/longhakly/handover.git ~/.agents/skills/handover
```

---

## 🛠️ Automated Safeguards Setup (OpenAI Codex CLI)

To enable automatic `< 5%` quota protection and turn-end recovery in the Codex CLI:

### 1. Enable PreToolUse Quota Guard (`hooks.json`)

Add the quota guard script to your project or global `hooks.json`:

```json
{
  "PreToolUse": [
    {
      "command": "python3 .agents/skills/handover/scripts/codex_quota_guard.py"
    }
  ]
}
```

*When remaining rate limits drop below 5%, the hook blocks tool calls (exit code `2`) and auto-generates `HANDOVER.md` before the process can crash.*

### 2. Enable Turn-End / Crash Watcher (`~/.codex/config.toml`)

Configure the turn-end notifier in `~/.codex/config.toml`:

```toml
notify = ["/path/to/handover/hooks/notify_handover_guard.sh", "turn-ended"]
```

---

## 💬 How to Use

### Manual Trigger in Chat
Simply ask your agent to hand over at any time:
```text
"handover"
"hand over to gemini"
"prepare handover doc"
```

The agent will stop modifying files, run `scripts/capture_handover_state.sh`, generate `HANDOVER.md`, and provide you with the continuation prompt.

### Resuming in Another Model
1. Open your target assistant (**Google Gemini**, **Claude Code**, or **Codex**).
2. Copy the continuation prompt from Section 9 of `HANDOVER.md` (or the agent's final chat output).
3. Paste it into the new assistant. The new model reads `HANDOVER.md` and immediately picks up where the previous one stopped.

### Post-Mortem Crash Recovery
If Codex abruptly exited due to a power outage, network loss, or rate limit cutoff before writing `HANDOVER.md`:

```bash
python3 .agents/skills/handover/scripts/recover_last_codex_session.py
```

This reads `~/.codex/sessions/`, reconstructs the last turn's state, and outputs a complete `HANDOVER.md`.

---

## 📂 Repository Structure

```text
handover/
├── SKILL.md                          # Main skill instructions and protocol definition
├── README.md                         # Documentation & integration guide
├── LICENSE                           # MIT License
├── templates/
│   └── HANDOVER_TEMPLATE.md          # Standardized 9-section handover template
├── scripts/
│   ├── capture_handover_state.sh     # Fast token-free git & workspace status capture
│   ├── codex_quota_guard.py          # PreToolUse hook monitoring rate limits (< 5%)
│   └── recover_last_codex_session.py # Transcript parser & HANDOVER.md generator
└── hooks/
    ├── notify_handover_guard.sh      # Codex turn-end notification hook
    └── hooks.json.example            # Sample PreToolUse hook configuration
```

---

## 🤝 Supported Ecosystem

* **OpenAI Codex CLI**
* **Google Gemini CLI / Antigravity**
* **Anthropic Claude Code**
* **Cursor / Windsurf / Copilot Workspace**

---

## 📜 License

Released under the [MIT License](LICENSE).
Created by [Long Hakly](https://github.com/longhakly).
