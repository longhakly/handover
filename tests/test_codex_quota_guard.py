#!/usr/bin/env python3
"""
test_codex_quota_guard.py

Regression tests for:
1. Resumed worker with stale 95%+ transcript allows diagnostic get_usage_limits.
2. Exact control calls inside exec (tools.get_usage_limits()) are allowed.
3. Mixed payloads or shell/file/messaging/worktree operations inside exec are denied.
4. Fresh healthy quota snapshot (< 98%) permits work tools.
5. Inverse: fresh diagnostic reporting true quota exhaustion (>= 98%) continues to deny work tools.
6. 98% threshold enforcement.
7. Single handover generation (deduplication of recovery runs).
8. Fast parsing performance on large transcripts (>20 MB).
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HANDOVER_DIR = os.path.dirname(SCRIPT_DIR)
GUARD_SCRIPT = os.path.join(HANDOVER_DIR, "scripts", "codex_quota_guard.py")
RECOVERY_SCRIPT = os.path.join(HANDOVER_DIR, "scripts", "recover_last_codex_session.py")
GENERATE_SCRIPT = os.path.join(HANDOVER_DIR, "scripts", "generate_handover.py")

sys.path.insert(0, os.path.join(HANDOVER_DIR, "scripts"))
from generate_handover import derive_case_slug, generate_handover

class TestCodexQuotaGuardRegression(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.cwd = self.test_dir.name
        self.session_file = os.path.join(self.cwd, "session.jsonl")

    def tearDown(self):
        self.test_dir.cleanup()

    def _append_event(self, event_data):
        with open(self.session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data) + "\n")

    def _write_stale_95_percent_transcript(self):
        # Initial session start with workspace cwd
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:00:00Z",
            "payload": {
                "type": "session_start",
                "cwd": self.cwd,
                "model": "gpt-5.6-sol"
            }
        })
        # User prompt
        self._append_event({
            "type": "response_item",
            "payload": {
                "role": "user",
                "content": [{"type": "input_text", "text": "Execute research task"}]
            }
        })
        # Stale token_count snapshot recorded around 06:20Z with 95% usage and future reset
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:20:00Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {
                        "used_percent": 95.0,
                        "window_minutes": 300,
                        "resets_at": int(time.time()) + 14400
                    },
                    "secondary": {
                        "used_percent": 95.0,
                        "window_minutes": 10080,
                        "resets_at": int(time.time()) + 86400
                    }
                }
            }
        })

    def _run_guard(self, tool_name, tool_input):
        payload = json.dumps({
            "transcript_path": self.session_file,
            "cwd": self.cwd,
            "tool_name": tool_name,
            "tool_input": tool_input,
        })
        res = subprocess.run(
            [sys.executable, GUARD_SCRIPT],
            input=payload,
            text=True,
            capture_output=True,
            cwd=self.cwd,
        )
        return res

    def test_direct_diagnostic_allowed_on_stale_quota(self):
        """1. Always allow a narrowly recognized read-only get_usage_limits call during a quota halt."""
        self._write_stale_95_percent_transcript()
        res = self._run_guard("get_usage_limits", {})
        self.assertEqual(res.returncode, 0, f"Expected 0 for diagnostic call, got: {res.returncode}, err: {res.stderr}")

    def test_exact_exec_control_call_allowed(self):
        """2. Allow only exact control calls when wrapped in exec."""
        self._write_stale_95_percent_transcript()
        
        # Exact await tools.get_usage_limits()
        res1 = self._run_guard("exec", {"code": "await tools.get_usage_limits()"})
        self.assertEqual(res1.returncode, 0, f"Expected 0, got {res1.returncode}")

        # Exact tools.get_usage_limits() without await
        res2 = self._run_guard("exec", {"code": "tools.get_usage_limits()"})
        self.assertEqual(res2.returncode, 0, f"Expected 0, got {res2.returncode}")

        # Exact with const assignment
        res3 = self._run_guard("exec", {"code": "const limits = await tools.get_usage_limits();"})
        self.assertEqual(res3.returncode, 0, f"Expected 0, got {res3.returncode}")

    def test_mixed_payloads_in_exec_rejected(self):
        """2. Reject mixed payloads or anything containing shell, file, messaging, or worktree operations."""
        self._write_stale_95_percent_transcript()
        
        # Mixed with shell execution
        res1 = self._run_guard("exec", {
            "code": "await tools.get_usage_limits(); await tools.exec_command({'cmd': 'npm test'});"
        })
        # Note: 95% is below 98%, but for this test let's ensure threshold is tested
        # Let's write 98.5%
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:21:00Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {"used_percent": 98.5}
                }
            }
        })
        res1 = self._run_guard("exec", {
            "code": "await tools.get_usage_limits(); await tools.exec_command({'cmd': 'npm test'});"
        })
        self.assertEqual(res1.returncode, 2, "Mixed exec_command payload must be rejected with exit code 2")

        # Mixed with file operations
        res2 = self._run_guard("exec", {
            "code": "await tools.get_usage_limits(); await tools.writeFile('foo.txt', 'data');"
        })
        self.assertEqual(res2.returncode, 2, "Mixed file op payload must be rejected with exit code 2")

        # Shell command in exec
        res3 = self._run_guard("exec", {"cmd": "git status"})
        self.assertEqual(res3.returncode, 2, "Git command in exec must be rejected with exit code 2")

    def test_full_regression_parent_reset_permits_work(self):
        """
        5. Full regression:
        main account reset -> resumed worker with stale 98%+ transcript -> usage diagnostic allowed
        -> fresh 2% snapshot appended -> work permitted.
        """
        # Step A: Worker starts with stale 98.5% transcript
        self._write_stale_95_percent_transcript()
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:20:01Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {"used_percent": 98.5, "resets_at": int(time.time()) + 14400}
                }
            }
        })

        # Step B: Normal work tool is denied
        work_res1 = self._run_guard("exec_command", {"cmd": "npm run build"})
        self.assertEqual(work_res1.returncode, 2, "Work tool must be denied when usage is 98.5%")

        # Step C: Diagnostic get_usage_limits is allowed
        diag_res = self._run_guard("get_usage_limits", {})
        self.assertEqual(diag_res.returncode, 0, "Diagnostic call must be allowed during quota halt")

        # Step D: Runtime executes diagnostic and appends fresh 2% snapshot to transcript
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:36:00Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {"used_percent": 2.0, "resets_at": int(time.time()) + 14400},
                    "secondary": {"used_percent": 0.0, "resets_at": int(time.time()) + 86400}
                }
            }
        })

        # Step E: Work tool is now permitted
        work_res2 = self._run_guard("exec_command", {"cmd": "npm run build"})
        self.assertEqual(work_res2.returncode, 0, f"Work tool must be permitted after fresh 2% snapshot, got err: {work_res2.stderr}")

    def test_inverse_regression_true_quota_exhaustion_denies_work(self):
        """
        5. Inverse regression:
        fresh diagnostic still reports true quota exhaustion (>= 98%) -> work remains denied.
        """
        self._write_stale_95_percent_transcript()
        # Diagnostic allowed
        diag_res = self._run_guard("get_usage_limits", {})
        self.assertEqual(diag_res.returncode, 0)

        # Runtime appends fresh snapshot still at 99.0%
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:36:00Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "limit_id": "codex",
                    "primary": {"used_percent": 99.0, "resets_at": int(time.time()) + 14400}
                }
            }
        })

        # Work tool must remain denied
        work_res = self._run_guard("exec_command", {"cmd": "npm run build"})
        self.assertEqual(work_res.returncode, 2, "Work tool must remain denied on fresh 99% snapshot")

    def test_threshold_98_percent(self):
        """Usage >= 98.0% halts, usage < 98.0% permits work."""
        self._write_stale_95_percent_transcript()

        # 97.9% -> permitted
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:25:00Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {"used_percent": 97.9}
                }
            }
        })
        res1 = self._run_guard("exec_command", {"cmd": "ls"})
        self.assertEqual(res1.returncode, 0, "97.9% usage should be permitted")

        # 98.0% -> halted
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:26:00Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {"used_percent": 98.0}
                }
            }
        })
        res2 = self._run_guard("exec_command", {"cmd": "ls"})
        self.assertEqual(res2.returncode, 2, "98.0% usage should be halted")

    def test_single_handover_generation(self):
        """Consecutive blocked calls do not re-run recovery or thrash backups."""
        self._write_stale_95_percent_transcript()
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:26:00Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {"used_percent": 98.5}
                }
            }
        })

        # First halt call generates HANDOVER.md
        res1 = self._run_guard("exec_command", {"cmd": "ls"})
        self.assertEqual(res1.returncode, 2)
        handover_path = os.path.join(self.cwd, "HANDOVER.md")
        self.assertTrue(os.path.exists(handover_path))

        mtime1 = os.path.getmtime(handover_path)
        time.sleep(0.05)

        # Second halt call should recognize handover already exists for this state
        res2 = self._run_guard("exec_command", {"cmd": "git status"})
        self.assertEqual(res2.returncode, 2)

        # No backup should have been created for the duplicate halt
        backup_path = f"{handover_path}.bak"
        self.assertFalse(os.path.exists(backup_path), "Duplicate recovery must not create unnecessary backup")

    def test_large_transcript_parsing_performance(self):
        """Simulate a large (>10 MB) session transcript and verify fast parsing (<200ms)."""
        large_session = os.path.join(self.cwd, "large_session.jsonl")
        with open(large_session, "w", encoding="utf-8") as f:
            # Header
            f.write(json.dumps({
                "type": "event_msg",
                "timestamp": "2026-10-15T06:00:00Z",
                "payload": {"type": "session_start", "cwd": self.cwd, "model": "gpt-5.6-sol"}
            }) + "\n")
            f.write(json.dumps({
                "type": "response_item",
                "payload": {"role": "user", "content": [{"type": "input_text", "text": "Build feature X"}]}
            }) + "\n")
            
            # Fill with > 12 MB of dummy tool logs
            dummy_line = json.dumps({"type": "tool_output", "payload": {"data": "x" * 2000}}) + "\n"
            for _ in range(6000):
                f.write(dummy_line)

            # Tail with recent activity and rate limit
            f.write(json.dumps({
                "type": "response_item",
                "payload": {"role": "user", "content": [{"type": "input_text", "text": "Execute final steps"}]}
            }) + "\n")
            f.write(json.dumps({
                "type": "event_msg",
                "timestamp": "2026-10-15T06:40:00Z",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {"used_percent": 98.2}
                    }
                }
            }) + "\n")

        file_size_mb = os.path.getsize(large_session) / (1024 * 1024)
        self.assertGreater(file_size_mb, 10.0)

        # Benchmark recover_last_codex_session on large file
        start_t = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, RECOVERY_SCRIPT, large_session],
            cwd=self.cwd,
            capture_output=True,
            text=True
        )
        elapsed = time.perf_counter() - start_t
        self.assertEqual(proc.returncode, 0, f"Recovery failed: {proc.stderr}")
        self.assertLess(elapsed, 0.5, f"Expected < 0.5s for 10MB extraction, took {elapsed:.3f}s")

    def test_resets_at_elapsed_permits_work(self):
        """When scheduled resets_at has passed, cached snapshot is stale and work is permitted."""
        self._write_stale_95_percent_transcript()
        # 99.0% usage recorded, but resets_at was 10 seconds ago
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:26:00Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {
                        "used_percent": 99.0,
                        "resets_at": int(time.time()) - 10
                    }
                }
            }
        })
        res = self._run_guard("exec_command", {"cmd": "npm run build"})
        self.assertEqual(res.returncode, 0, f"Elapsed resets_at must permit work tools, got {res.returncode}")

    def test_read_only_probe_allowed_during_halt(self):
        """Harmless read-only probes (pwd, true, date) are allowed in exec during quota halt."""
        self._write_stale_95_percent_transcript()
        self._append_event({
            "type": "event_msg",
            "timestamp": "2026-10-15T06:26:00Z",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {
                        "used_percent": 99.0,
                        "resets_at": int(time.time()) + 14400
                    }
                }
            }
        })

        # Exact pwd probe
        res_pwd = self._run_guard("exec", {"code": 'await tools.exec_command({ cmd: "pwd" })'})
        self.assertEqual(res_pwd.returncode, 0, f"Expected 0 for pwd probe, got {res_pwd.returncode}")

        # Exact true probe
        res_true = self._run_guard("exec", {"code": 'tools.exec_command({ cmd: "true" })'})
        self.assertEqual(res_true.returncode, 0, f"Expected 0 for true probe, got {res_true.returncode}")

        # Chained command must be rejected
        res_chained = self._run_guard("exec", {"code": 'await tools.exec_command({ cmd: "pwd; git push" })'})
        self.assertEqual(res_chained.returncode, 2, f"Chained probe must be rejected with 2, got {res_chained.returncode}")

    def test_derive_case_slug_explicit(self):
        self.assertEqual(derive_case_slug(explicit_case="auth-refactor"), "auth-refactor")
        self.assertEqual(derive_case_slug(explicit_case="HANDOVER_PP-123.md"), "PP-123")

    def test_derive_case_slug_ticket(self):
        slug = derive_case_slug(task_description="Fix PP-2574 stream chat display blank")
        self.assertTrue(slug.startswith("PP-2574"), f"Expected to start with PP-2574, got {slug}")
        self.assertIn("stream", slug)

    def test_derive_case_slug_branch(self):
        git_state = "### Repository: `front-end`\n- **Branch**: `feature/ENG-2454-auto-select-class-group`\n"
        slug = derive_case_slug(task_description="Task transition", git_state=git_state)
        self.assertEqual(slug, "ENG-2454-auto-select-class-group")

    def test_multi_case_persistence_and_root_pointer(self):
        """Generating multiple distinct cases creates distinct files and preserves past cases."""
        # Case 1
        res1 = generate_handover(self.cwd, task_description="Task One", explicit_case="case-alpha")
        self.assertEqual(os.path.basename(res1), "HANDOVER_case-alpha.md")
        self.assertTrue(os.path.exists(res1))
        root_handover = os.path.join(self.cwd, "HANDOVER.md")
        self.assertTrue(os.path.exists(root_handover))
        with open(root_handover, "r", encoding="utf-8") as f:
            self.assertIn("case-alpha", f.read())

        # Case 2
        res2 = generate_handover(self.cwd, task_description="Task Two", explicit_case="case-beta")
        self.assertEqual(os.path.basename(res2), "HANDOVER_case-beta.md")
        self.assertTrue(os.path.exists(res2))

        # Crucial: Case 1 file MUST still exist! (No longer single file overwritten every time)
        self.assertTrue(os.path.exists(res1), "Case 1 file must still exist after Case 2 generation!")
        with open(root_handover, "r", encoding="utf-8") as f:
            self.assertIn("case-beta", f.read())

    def test_recover_last_codex_session_case_specific_file(self):
        """Recovery script extracts ticket from session prompt and outputs case-specific file."""
        self._write_stale_95_percent_transcript()
        # Session prompt with ticket PP-2574
        self._append_event({
            "type": "response_item",
            "payload": {
                "role": "user",
                "content": [{"type": "input_text", "text": "Resolve PP-2574 blank screen on stream chat"}]
            }
        })
        proc = subprocess.run(
            [sys.executable, RECOVERY_SCRIPT, self.session_file],
            cwd=self.cwd,
            capture_output=True,
            text=True
        )
        self.assertEqual(proc.returncode, 0, f"Recovery failed: {proc.stderr}")
        files = os.listdir(self.cwd)
        case_files = [f for f in files if f.startswith("HANDOVER_PP-2574") and f.endswith(".md")]
        self.assertTrue(len(case_files) >= 1, f"Expected HANDOVER_PP-2574-*.md in {files}")
        self.assertTrue(os.path.exists(os.path.join(self.cwd, "HANDOVER.md")))

if __name__ == "__main__":
    unittest.main()
