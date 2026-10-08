# Handover (`HANDOVER.md`)

> **Zero-loss context handovers and automated quota protection for AI coding agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Supported Agents](https://img.shields.io/badge/Agents-Claude%20%7C%20Gemini%20%7C%20Codex%20%7C%20Cursor-orange.svg)](#-setup-by-agent)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-green.svg)](#-quick-install)

**Handover** is a portable, multi-agent skill and framework that solves the two biggest pain points in AI pair-programming:
1. **The 5% Token & Rate-Limit Cliff**: Agents running out of tokens or hitting API rate limits (HTTP 429) mid-turn, leaving broken syntax, dirty git states, and lost context.
2. **Cross-Model Switching Friction**: Having to manually re-explain task status, completed milestones, and immediate next steps when switching between assistants (e.g., **Anthropic Claude Code** $\leftrightarrow$ **Google Gemini** $\leftrightarrow$ **OpenAI Codex** $\leftrightarrow$ **Cursor**).

Whenever limits approach exhaustion—or whenever you trigger a handover—this framework halts active edits, captures workspace state, scrubs secrets, and writes a production-ready **`HANDOVER.md`** with an exact continuation prompt for the next assistant.

---

## ⚡ Key Features

* 🔄 **Zero-Loss Model Transitions**: Move smoothly between models (Claude $\leftrightarrow$ Gemini $\leftrightarrow$ Codex $\leftrightarrow$ Cursor) with a single copy-paste continuation prompt.
* 📋 **Standardized 9-Section Specification**: Persists **Problem Description**, **Current Behavior**, **Desired Behavior**, **Milestones**, **Uncommitted Diffs**, and **Ordered Next Steps**.
* 🛡️ **Automated Quota Guard (Codex CLI)**: Intercepts tool calls at 95% rate-limit usage, halting cleanly before unexpected 429 crashes occur.
* 💬 **Native Slash Command (Claude Code)**: Includes `.claude/commands/handover.md` so Claude users can simply type `/handover`.
* 🔒 **Automatic Secret Redaction**: Built-in sanitization redacts Bearer tokens, JWTs, and API credentials (`Bearer [REDACTED_JWT]`).
* 🚀 **Smart Stack Auto-Detection**: Automatically detects test and build commands across **Node.js / TypeScript**, **Python**, **Rust**, **Go**, and **Makefiles**.
* 🧹 **Clean Git Parsing**: Isolates modified and untracked files cleanly from `git status` without polluting reports with diffstat markers (`+++++`, `deletions(-)`).
* 🗂️ **Multi-Repo Workspace Support**: Recursively inspects and reports dirty state across mono-repos and multi-repository project roots.
* 🖥️ **Universal Terminal Runner**: Run `generate_handover.py` directly from your shell regardless of which assistant you use.

---

## 🚀 Quick Install

Clone this repository into your project and run the multi-agent installer:

```bash
# Clone the repository
git clone https://github.com/longhakly/handover.git .handover-src

# Run the installer for your project (sets up Claude, Gemini, Codex, and Cursor)
bash .handover-src/install.sh --all

# Clean up source repo
rm -rf .handover-src
```

*(Alternatively, copy only what you need using the specific agent guides below).*

---

## 🤖 Setup by Agent

### 🟣 1. Anthropic Claude Code

Claude Code supports custom slash commands and `CLAUDE.md` instructions:

1. **Install Slash Command**:
   ```bash
   mkdir -p .claude/commands
   curl -fsSL https://raw.githubusercontent.com/longhakly/handover/main/.claude/commands/handover.md -o .claude/commands/handover.md
   ```
2. **(Optional) Add to `CLAUDE.md`**:
   Add this snippet to your project's `CLAUDE.md`:
   ```markdown
   ## Handover Protocol
   When the user asks to "handover" or when context limits approach exhaustion:
   1. Halt modifying files immediately.
   2. Run `bash scripts/capture_handover_state.sh` to capture git state.
   3. Generate `HANDOVER.md` in root with Problem Description, Current vs Desired Behavior, and next steps.
   4. Conclude with a copy-pasteable continuation prompt for the next assistant.
   ```
3. **Usage in Chat**:
   Simply type:
   ```text
   /handover
   ```

---

### 🔵 2. Google Gemini & Antigravity

Gemini CLI and Antigravity auto-discover skills placed in `.agents/skills/`:

1. **Install Skill**:
   ```bash
   mkdir -p .agents/skills
   git clone https://github.com/longhakly/handover.git .agents/skills/handover
   ```
2. **Usage in Chat**:
   Simply ask Gemini:
   ```text
   "handover to claude"
   # or
   "prepare handover doc"
   ```
   Gemini will automatically read `SKILL.md`, capture git state, write `HANDOVER.md`, and output the continuation prompt.

---

### 🟢 3. OpenAI Codex CLI

Codex supports skills plus automated background rate-limit protection:

1. **Install Skill**:
   ```bash
   mkdir -p .agents/skills
   git clone https://github.com/longhakly/handover.git .agents/skills/handover
   ```
2. **Enable Quota Guard Hook (`hooks.json`)**:
   Add this to your project or global `hooks.json` to automatically stop execution at 95% quota:
   ```json
   {
     "PreToolUse": [
       {
         "command": "python3 .agents/skills/handover/scripts/codex_quota_guard.py"
       }
     ]
   }
   ```
3. **(Optional) Enable Crash Watcher (`~/.codex/config.toml`)**:
   ```toml
   notify = ["/path/to/handover/hooks/notify_handover_guard.sh", "turn-ended"]
   ```
4. **Post-Mortem Crash Recovery**:
   If Codex terminated abruptly before writing the file, reconstruct state directly from session logs:
   ```bash
   python3 .agents/skills/handover/scripts/recover_last_codex_session.py
   ```

---

### 🟡 4. Cursor / Windsurf / Copilot Workspace

Add the handover instruction to `.cursorrules` or `.windsurfrules`:

```markdown
# Handover Protocol
When asked for a "handover" or "prepare handover doc":
1. Stop editing files immediately.
2. Run `bash scripts/capture_handover_state.sh` (or `.agents/skills/handover/scripts/capture_handover_state.sh`).
3. Write `HANDOVER.md` in project root with Problem Description, Current Behavior, Desired Behavior, and uncommitted git diffs.
4. Output the continuation prompt for the next assistant.
```

---

### ⚪ 5. Standalone Terminal CLI (Any Tool / No Agent)

You can also generate `HANDOVER.md` directly from your terminal at any time without waiting for an LLM:

```bash
python3 scripts/generate_handover.py "Short summary of current task"
```

This immediately inspects git state, detects test runners, scrubs secrets, and outputs a complete `HANDOVER.md`.

---

## 📄 Structure of `HANDOVER.md`

Every handover generates a standardized, single-file context ledger:

```markdown
# Session Handover Document

## 1. Executive Context
- Task, outgoing model, handover reason, timestamp, branch.

## 2. Problem & Behavior Specification
- **Description**: What is being built or fixed.
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

## 📂 Repository Structure

```text
handover/
├── SKILL.md                          # Universal skill specification
├── README.md                         # Documentation & multi-agent guide
├── LICENSE                           # MIT License
├── install.sh                        # Multi-agent installer script
├── .claude/
│   └── commands/
│       └── handover.md               # Native Claude Code slash command (/handover)
├── rules/
│   ├── CLAUDE.md                     # Snippet for project CLAUDE.md
│   ├── cursorrules.example           # Snippet for .cursorrules / .windsurfrules
│   └── AGENTS.md                     # Snippet for project AGENTS.md
├── templates/
│   └── HANDOVER_TEMPLATE.md          # Standardized 9-section handover template
├── scripts/
│   ├── capture_handover_state.sh     # Fast token-free git & workspace status capture
│   ├── generate_handover.py          # Universal standalone HANDOVER.md generator
│   ├── codex_quota_guard.py          # PreToolUse hook monitoring rate limits (< 5%)
│   └── recover_last_codex_session.py # Codex JSONL transcript parser & crash recovery
└── hooks/
    ├── notify_handover_guard.sh      # Codex turn-end notification hook
    └── hooks.json.example            # Sample PreToolUse hook configuration
```

---

## 🤝 Supported Ecosystem

* **Anthropic Claude Code** (`/handover` command & `CLAUDE.md`)
* **Google Gemini CLI & Antigravity** (Native `.agents/skills/`)
* **OpenAI Codex CLI** (PreToolUse hook & crash recovery)
* **Cursor, Windsurf & GitHub Copilot** (`.cursorrules` & project instructions)
* **Universal Terminal CLI** (Standalone Python runner)

---

## 📜 License

Released under the [MIT License](LICENSE).
Created by [Long Hakly](https://github.com/longhakly).
