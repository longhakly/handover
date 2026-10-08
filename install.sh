#!/usr/bin/env bash
# install.sh
# Multi-agent installer for Handover (Claude Code, Gemini, Codex, Cursor)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${PWD}"

echo "=========================================="
echo "  Handover Installer (Multi-Agent Setup)  "
echo "=========================================="
echo "Target project directory: ${TARGET_DIR}"
echo ""

install_claude() {
    echo "-> Installing for Claude Code..."
    mkdir -p "${TARGET_DIR}/.claude/commands"
    cp "${SCRIPT_DIR}/.claude/commands/handover.md" "${TARGET_DIR}/.claude/commands/handover.md"
    echo "   ✓ Created .claude/commands/handover.md (Type /handover in Claude Code)"
}

install_gemini_and_codex() {
    echo "-> Installing for Gemini, Antigravity, and Codex..."
    mkdir -p "${TARGET_DIR}/.agents/skills/handover/scripts"
    mkdir -p "${TARGET_DIR}/.agents/skills/handover/templates"
    cp "${SCRIPT_DIR}/SKILL.md" "${TARGET_DIR}/.agents/skills/handover/SKILL.md"
    cp -r "${SCRIPT_DIR}/templates/"* "${TARGET_DIR}/.agents/skills/handover/templates/"
    cp -r "${SCRIPT_DIR}/scripts/"* "${TARGET_DIR}/.agents/skills/handover/scripts/"
    echo "   ✓ Installed skill to .agents/skills/handover/"
}

install_cursor() {
    echo "-> Setting up Cursor / Windsurf rules..."
    if [ ! -f "${TARGET_DIR}/.cursorrules" ]; then
        cp "${SCRIPT_DIR}/rules/cursorrules.example" "${TARGET_DIR}/.cursorrules"
        echo "   ✓ Created .cursorrules"
    else
        echo "   ℹ .cursorrules already exists. Snippet available in rules/cursorrules.example"
    fi
}

MODE="${1:---all}"

case "$MODE" in
    --claude)
        install_claude
        ;;
    --gemini)
        install_gemini_and_codex
        ;;
    --codex)
        install_gemini_and_codex
        ;;
    --cursor)
        install_cursor
        ;;
    --all|*)
        install_claude
        install_gemini_and_codex
        install_cursor
        ;;
esac

echo ""
echo "=========================================="
echo "  Installation Complete! 🎉               "
echo "=========================================="
echo "How to use:"
echo "• Claude Code : Type /handover"
echo "• Gemini / AGY: Type 'handover'"
echo "• Codex CLI   : Type 'handover' (or configure PreToolUse in hooks.json)"
echo "• Terminal CLI: python3 .agents/skills/handover/scripts/generate_handover.py"
echo "=========================================="
