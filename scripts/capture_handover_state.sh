#!/usr/bin/env bash
# capture_handover_state.sh
# Inspects git repositories and working tree state across single-repo or multi-repo workspaces
# to generate a clean markdown summary for HANDOVER.md without wasting model tokens.

set -euo pipefail

TARGET_OUTPUT="${1:-}"

capture_repo_state() {
    local repo_dir="$1"
    local repo_name
    repo_name=$(basename "$repo_dir")

    echo "### Repository: \`$repo_name\`"
    
    # Branch & commit
    local branch
    branch=$(git -C "$repo_dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    local commit
    commit=$(git -C "$repo_dir" rev-parse --short HEAD 2>/dev/null || echo "none")
    echo "- **Branch**: \`$branch\` (\`$commit\`)"

    # Status summary
    local status_output
    status_output=$(git -C "$repo_dir" status -s 2>/dev/null || true)
    if [ -z "$status_output" ]; then
        echo "- **Status**: Clean working tree"
    else
        echo "- **Modified / Untracked Files**:"
        echo '```text'
        echo "$status_output"
        echo '```'
    fi

    # Diff stat summary if dirty
    local diff_stat
    diff_stat=$(git -C "$repo_dir" diff --stat 2>/dev/null || true)
    if [ -n "$diff_stat" ]; then
        echo "- **Diff Stats**:"
        echo '```text'
        echo "$diff_stat"
        echo '```'
    fi
    echo ""
}

generate_report() {
    echo "<!-- AUTO-CAPTURED WORKSPACE STATE AT $(date -u +"%Y-%m-%d %H:%M:%SZ") -->"
    echo ""

    # Check if root is a git repository
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        capture_repo_state "."
    else
        # Inspect immediate subdirectories for git repositories (multi-repo workspace)
        local found=0
        for dir in */; do
            if [ -d "$dir/.git" ]; then
                capture_repo_state "$dir"
                found=1
            fi
        done
        if [ "$found" -eq 0 ]; then
            echo "- No active git repositories detected in workspace root or immediate subdirectories."
            echo ""
        fi
    fi
}

if [ -n "$TARGET_OUTPUT" ]; then
    generate_report >> "$TARGET_OUTPUT"
    echo "Captured workspace state into $TARGET_OUTPUT"
else
    generate_report
fi
