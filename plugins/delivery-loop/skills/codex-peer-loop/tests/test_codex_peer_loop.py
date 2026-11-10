from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "codex_peer_loop.py"
SPEC = importlib.util.spec_from_file_location("codex_peer_loop", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
codex_peer_loop = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = codex_peer_loop
SPEC.loader.exec_module(codex_peer_loop)


class ConfigurationDefaultsTests(unittest.TestCase):
    def test_model_fallback_is_gpt_6_astra(self) -> None:
        self.assertEqual(codex_peer_loop.DEFAULT_MODEL_FALLBACK, "gpt-6-astra")

    def test_defaults_to_gpt_6_astra_at_auto_medium_effort(self) -> None:
        args = codex_peer_loop.parse_args(
            ["--question", "Review this change."],
            environ={},
        )

        self.assertEqual(args.model, "gpt-6-astra")
        self.assertEqual(args.effort_requested, "auto")
        self.assertEqual(args.effort, "medium")

    def test_auto_effort_follows_review_work_and_phase_scope(self) -> None:
        resolve = codex_peer_loop.resolve_effort
        cases = {
            # (complexity, phase) -> effort; full-scope phases climb one rung.
            ("routine", "plan"): "high",
            ("routine", "agent-config"): "high",
            ("routine", "commit-gate"): "high",
            ("routine", "verification"): "medium",
            ("routine", "review"): "medium",
            ("routine", "implementation"): "medium",
            # A phase label never lowers effort; Claude lowers complexity.
            ("routine", "post-commit"): "medium",
            ("routine", "self-review"): "medium",
            ("trivial", "verification"): "low",
            ("trivial", "plan"): "medium",
            ("complex", "commit-gate"): "xhigh",
            ("complex", "verification"): "high",
            ("critical", "verification"): "xhigh",
            # Auto clamps at xhigh; max and ultra stay explicit-only.
            ("critical", "plan"): "xhigh",
        }
        for (complexity, phase), expected in cases.items():
            with self.subTest(complexity=complexity, phase=phase):
                self.assertEqual(resolve("auto", phase, complexity), expected)
        self.assertEqual(resolve("xhigh", "review", "trivial"), "xhigh")
        self.assertEqual(resolve("max", "post-commit", "trivial"), "max")

    def test_iteration_and_skepticism_do_not_change_effort(self) -> None:
        def effort(*flags: str) -> str:
            return codex_peer_loop.parse_args(
                ["--question", "q", *flags], environ={}
            ).effort

        # The first code gate after a plan pass is still a full review.
        self.assertEqual(effort("--phase", "commit-gate", "--iteration", "2"), "high")
        self.assertEqual(effort("--phase", "commit-gate", "--iteration", "1"), "high")
        self.assertEqual(effort("--phase", "review", "--skepticism", "blocking"), "medium")

    def test_complexity_is_kept_on_resume(self) -> None:
        args = codex_peer_loop.parse_args(
            ["--question", "Review this plan.", "--phase", "plan", "--complexity", "complex"],
            environ={},
        )
        args.codex_bin = "/path/to/codex"
        self.assertEqual(args.effort, "xhigh")

        resume_tokens = shlex.split(codex_peer_loop.next_command(args))
        resumed = codex_peer_loop.parse_args(resume_tokens[1:], environ={})

        self.assertEqual(resumed.complexity, "complex")
        self.assertEqual(resumed.effort, "high")

    def test_explicit_effort_overrides_auto_and_is_kept_on_resume(self) -> None:
        args = codex_peer_loop.parse_args(
            ["--question", "Review this change.", "--phase", "plan", "--effort", "xhigh"],
            environ={},
        )
        args.codex_bin = "/path/to/codex"

        self.assertEqual(args.effort, "xhigh")
        resume_tokens = shlex.split(codex_peer_loop.next_command(args))
        resumed = codex_peer_loop.parse_args(resume_tokens[1:], environ={})
        self.assertEqual(resumed.effort, "xhigh")

    def test_auto_resume_lets_the_follow_up_pass_pick_its_own_effort(self) -> None:
        args = codex_peer_loop.parse_args(
            ["--question", "Review this plan.", "--phase", "plan"],
            environ={},
        )
        args.codex_bin = "/path/to/codex"
        self.assertEqual(args.effort, "high")

        resume_tokens = shlex.split(codex_peer_loop.next_command(args))
        resumed = codex_peer_loop.parse_args(resume_tokens[1:], environ={})

        self.assertEqual(resumed.effort_requested, "auto")
        self.assertEqual(resumed.phase, "verification")
        self.assertEqual(resumed.effort, "medium")

    def test_environment_can_override_model_and_effort(self) -> None:
        args = codex_peer_loop.parse_args(
            ["--question", "Review this change."],
            environ={
                "CODEX_PEER_LOOP_MODEL": "gpt-5.6-terra",
                "CODEX_PEER_LOOP_EFFORT": "xhigh",
            },
        )

        self.assertEqual(args.model, "gpt-5.6-terra")
        self.assertEqual(args.effort, "xhigh")

    def test_rejects_non_positive_runtime_limits_and_invalid_score(self) -> None:
        invalid_arguments = (
            ["--iteration", "0"],
            ["--timeout-seconds", "0"],
            ["--context-bytes", "0"],
            ["--context-total-bytes", "-1"],
            ["--required-min-score", "11"],
        )

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with (
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    codex_peer_loop.parse_args(
                        ["--question", "Review this change.", *arguments],
                        environ={},
                    )

    def test_timeout_fallback_allows_sixty_minutes(self) -> None:
        self.assertGreaterEqual(codex_peer_loop.DEFAULT_TIMEOUT_SECONDS_FALLBACK, 3600)


class GreenGateTests(unittest.TestCase):
    def test_accepts_green_result_at_required_score(self) -> None:
        output = "VERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 8\n"

        self.assertIsNone(codex_peer_loop.green_gate_failure(output, 8))

    def test_rejects_non_green_result(self) -> None:
        output = "GREEN_LIGHT: no\nMIN_SCORE: 10\n"

        failure = codex_peer_loop.green_gate_failure(output, 8)

        self.assertIsNotNone(failure)
        self.assertIn("header invalid", failure.lower())

    def test_rejects_missing_score(self) -> None:
        output = "VERDICT: green\nGREEN_LIGHT: yes\n"

        failure = codex_peer_loop.green_gate_failure(output, 8)

        self.assertIsNotNone(failure)
        self.assertIn("header invalid", failure.lower())

    def test_rejects_score_below_threshold(self) -> None:
        output = "VERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 7\n"

        self.assertEqual(
            codex_peer_loop.green_gate_failure(output, 8),
            "Codex MIN_SCORE 7 is below required minimum 8.",
        )

    def test_rejects_out_of_range_score(self) -> None:
        output = "VERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 11\n"

        failure = codex_peer_loop.green_gate_failure(output, 8)

        self.assertIsNotNone(failure)
        self.assertIn("header invalid", failure.lower())

    def test_rejects_non_green_verdict(self) -> None:
        output = "VERDICT: changes_required\nGREEN_LIGHT: yes\nMIN_SCORE: 10\n"

        self.assertEqual(
            codex_peer_loop.green_gate_failure(output, 8),
            "Codex did not return VERDICT: green.",
        )

    def test_rejects_later_green_example_after_non_green_header(self) -> None:
        output = (
            "VERDICT: changes_required\n"
            "GREEN_LIGHT: no\n"
            "MIN_SCORE: 10\n\n"
            "Quoted example:\n"
            "VERDICT: green\n"
            "GREEN_LIGHT: yes\n"
            "MIN_SCORE: 10\n"
        )

        failure = codex_peer_loop.green_gate_failure(output, 8)

        self.assertEqual(failure, "Codex did not return GREEN_LIGHT: yes.")

    def test_accepts_leading_whitespace_before_green_header(self) -> None:
        output = "\n  \nVERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 9\n"

        self.assertIsNone(codex_peer_loop.green_gate_failure(output, 8))

    def test_later_score_restatement_does_not_override_green_header(self) -> None:
        output = (
            "VERDICT: green\n"
            "GREEN_LIGHT: yes\n"
            "MIN_SCORE: 9\n\n"
            "## Scorecard\n"
            "MIN_SCORE: 5\n"
        )

        self.assertIsNone(codex_peer_loop.green_gate_failure(output, 8))


class CodexExecutableTests(unittest.TestCase):
    def test_resolves_explicit_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            executable = Path(temporary_directory) / "codex"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

            resolved = codex_peer_loop.resolve_codex_bin(str(executable))

        self.assertEqual(resolved, str(executable.resolve()))

    def test_rejects_missing_configured_executable(self) -> None:
        missing = Path(tempfile.gettempdir()) / "missing-codex-peer-loop-binary"
        if missing.exists():
            self.skipTest(f"Unexpected executable exists: {missing}")

        with self.assertRaises(SystemExit):
            codex_peer_loop.resolve_codex_bin(os.fspath(missing))


class CodexSessionContinuityTests(unittest.TestCase):
    def test_identity_status_is_unverified_when_codex_did_not_complete(self) -> None:
        self.assertEqual(
            codex_peer_loop.identity_check_status(17, None),
            "unverified",
        )
        self.assertEqual(
            codex_peer_loop.identity_check_status(0, "identity mismatch"),
            "failed",
        )
        self.assertEqual(codex_peer_loop.identity_check_status(0, None), "passed")

    def test_failed_provider_receipt_marks_identity_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_codex = root / "codex"
            fake_codex.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            result = subprocess.run(
                [
                    sys.executable,
                    os.fspath(SCRIPT),
                    "--new-session",
                    "--session",
                    "failed-receipt-test",
                    "--question",
                    "Review the receipt contract.",
                    "--codex-bin",
                    os.fspath(fake_codex),
                    "--no-print-next-command",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            status_files = list((root / ".codex" / "artifacts").glob("*.status"))
            status = status_files[0].read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 17)
        self.assertEqual(len(status_files), 1)
        self.assertIn("thread_identity_status=unverified", status)

    def test_session_scope_is_the_main_worktree(self) -> None:
        if not shutil.which("git"):
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory).resolve()
            main = base / "main"
            main.mkdir()
            git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
            subprocess.run([*git, "init", "-q", "-b", "main"], cwd=main, check=True)
            (main / "f").write_text("x", encoding="utf-8")
            subprocess.run([*git, "add", "f"], cwd=main, check=True)
            subprocess.run([*git, "commit", "-q", "-m", "init"], cwd=main, check=True)
            linked = base / "lane"
            subprocess.run(
                [*git, "worktree", "add", "-q", os.fspath(linked), "-b", "lane"],
                cwd=main,
                check=True,
            )
            nested = linked / "backend"
            nested.mkdir()

            self.assertEqual(codex_peer_loop.session_scope_root(main), main)
            self.assertEqual(codex_peer_loop.session_scope_root(linked), main)
            self.assertEqual(
                codex_peer_loop.session_id_path("gate", main),
                codex_peer_loop.session_id_path(
                    "gate", codex_peer_loop.session_scope_root(linked)
                ),
            )
            plain = base / "plain"
            plain.mkdir()
            self.assertEqual(codex_peer_loop.session_scope_root(plain), plain)

    def test_missing_state_names_the_repository_that_has_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory).resolve()
            state = base / "state"
            with mock.patch.object(codex_peer_loop, "STATE_DIR", state):
                codex_peer_loop.write_stored_thread_id(
                    "gate", "019f9532-bc8d-7410-b6cc-3941d027574a", base / "repo-a"
                )
                others = codex_peer_loop.other_scopes_for_session(
                    "gate", base / "repo-b"
                )
                self.assertEqual(others, [str(base / "repo-a")])
                self.assertEqual(
                    codex_peer_loop.other_scopes_for_session("gate", base / "repo-a"),
                    [],
                )
                codex_peer_loop.invalidate_stored_thread_id("gate", base / "repo-a")
                self.assertEqual(
                    codex_peer_loop.other_scopes_for_session("gate", base / "repo-b"),
                    [],
                )

    def test_session_lock_refuses_a_concurrent_pass_until_released(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state = Path(temporary_directory) / "state"
            root = Path("/tmp/repo-lock")
            with mock.patch.object(codex_peer_loop, "STATE_DIR", state):
                lock = codex_peer_loop.acquire_session_lock("gate", root)
                with self.assertRaises(SystemExit) as raised:
                    codex_peer_loop.acquire_session_lock("gate", root)
                self.assertIn("already has a running pass", str(raised.exception))
                self.assertIn(str(os.getpid()), str(raised.exception))
                codex_peer_loop.release_session_lock(lock)
                again = codex_peer_loop.acquire_session_lock("gate", root)
                codex_peer_loop.release_session_lock(again)

    def test_state_path_is_scoped_to_repository_root(self) -> None:
        first = codex_peer_loop.session_id_path(
            "shared-name",
            Path("/tmp/repo-a"),
        )
        second = codex_peer_loop.session_id_path(
            "shared-name",
            Path("/tmp/repo-b"),
        )
        colliding_slug = codex_peer_loop.session_id_path(
            "shared/name",
            Path("/tmp/repo-a"),
        )
        same_slug = codex_peer_loop.session_id_path(
            "shared-name",
            Path("/tmp/repo-a"),
        )

        self.assertNotEqual(first, second)
        self.assertNotEqual(colliding_slug, same_slug)

    def test_legacy_unscoped_state_fails_with_migration_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state_dir = root / "state"
            state_dir.mkdir()
            session = "legacy-review"
            (state_dir / f"{codex_peer_loop.slugify(session)}.session_id").write_text(
                "019f9532-bc8d-7410-b6cc-3941d027574a\n",
                encoding="utf-8",
            )
            fake_codex = root / "codex"
            fake_codex.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            result = subprocess.run(
                [
                    sys.executable,
                    os.fspath(SCRIPT),
                    "--session",
                    session,
                    "--question",
                    "Resume safely.",
                    "--codex-bin",
                    os.fspath(fake_codex),
                    "--no-print-next-command",
                ],
                cwd=root,
                env={
                    **os.environ,
                    "CODEX_PEER_LOOP_STATE_DIR": os.fspath(state_dir),
                },
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("legacy unscoped", result.stderr.lower())
        self.assertIn("--new-session", result.stderr)
        self.assertNotEqual(result.returncode, 99)

    def test_thread_identity_comes_only_from_thread_started_event(self) -> None:
        unrelated_thread_id = "019f9532-bc8d-7410-b6cc-3941d027574a"
        stdout = (
            '{"type":"item.completed","item":{"type":"agent_message",'
            f'"thread_id":"{unrelated_thread_id}","text":"example"}}'
        )

        self.assertIsNone(codex_peer_loop.extract_thread_id(stdout))

    def test_thread_identity_rejects_non_objects_and_malformed_uuid(self) -> None:
        stdout = "\n".join(
            [
                "[]",
                "null",
                '"text"',
                '{"type":"thread.started","thread_id":"a---------------"}',
            ]
        )

        self.assertIsNone(codex_peer_loop.extract_thread_id(stdout))

    def test_message_fallback_uses_last_agent_message(self) -> None:
        stdout = "\n".join(
            [
                "[]",
                '{"type":"item.completed","item":{"type":"agent_message",'
                '"text":"progress"}}',
                '{"type":"item.completed","item":{"type":"agent_message",'
                '"text":"VERDICT: green\\nGREEN_LIGHT: yes\\nMIN_SCORE: 9"}}',
            ]
        )

        self.assertEqual(
            codex_peer_loop.extract_codex_messages(stdout),
            "VERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 9",
        )

    def test_runner_rejects_missing_or_mismatched_thread_identity(self) -> None:
        first_thread_id = "019f9532-bc8d-7410-b6cc-3941d027574a"
        wrong_thread_id = "119f9532-bc8d-7410-b6cc-3941d027574a"

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state_dir = root / "state"
            args_log = root / "codex-args.txt"
            fake_codex = root / "codex"

            def write_fake(thread_id: str | None) -> None:
                thread_event = (
                    "printf '%s\\n' "
                    f'\'{{"type":"thread.started","thread_id":"{thread_id}"}}\'\n'
                    if thread_id is not None
                    else ""
                )
                fake_codex.write_text(
                    "#!/bin/sh\n"
                    f": > '{args_log}'\n"
                    'for argument in "$@"; do\n'
                    f"  printf '%s\\n' \"$argument\" >> '{args_log}'\n"
                    "done\n"
                    f"{thread_event}"
                    "printf '%s\\n' "
                    '\'{"type":"item.completed","item":'
                    '{"type":"agent_message","text":'
                    '"VERDICT: green\\\\nGREEN_LIGHT: yes\\\\nMIN_SCORE: 10"}}\'\n',
                    encoding="utf-8",
                )
                fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            environment = {
                **os.environ,
                "CODEX_PEER_LOOP_STATE_DIR": os.fspath(state_dir),
            }
            base_command = [
                sys.executable,
                os.fspath(SCRIPT),
                "--session",
                "identity-contract-test",
                "--question",
                "Review the session contract.",
                "--codex-bin",
                os.fspath(fake_codex),
                "--no-print-next-command",
            ]

            write_fake(first_thread_id)
            first = subprocess.run(
                [*base_command, "--new-session"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            write_fake(None)
            missing = subprocess.run(
                [*base_command, "--new-session"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            stored_path = state_dir / (
                codex_peer_loop.scoped_session_key("identity-contract-test", root)
                + ".session_id"
            )
            self.assertFalse(stored_path.exists())
            stored_path.write_text(first_thread_id + "\n", encoding="utf-8")

            write_fake(wrong_thread_id)
            mismatched = subprocess.run(
                base_command,
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            resumed_arguments = args_log.read_text(encoding="utf-8").splitlines()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(missing.returncode, 4)
        self.assertIn("did not report", missing.stderr.lower())
        self.assertEqual(mismatched.returncode, 4)
        self.assertIn(first_thread_id, resumed_arguments)
        self.assertIn("identity mismatch", mismatched.stderr.lower())


class BackgroundRunTrackingTests(unittest.TestCase):
    THREAD_ID = "019f9532-bc8d-7410-b6cc-3941d027574a"
    GREEN = "VERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 10"
    NON_GREEN = "VERDICT: changes_required\nGREEN_LIGHT: no\nMIN_SCORE: 5"

    def _write_fake_codex(
        self,
        root: Path,
        verdict: str | None = None,
        block_on: Path | None = None,
    ) -> Path:
        """Write a Codex stand-in.

        Python rather than shell: the agent message carries real newlines, and
        only json.dumps escapes them correctly for the runner's JSONL parser.
        """
        fake_codex = root / "codex"
        body = [
            f"#!{sys.executable}",
            "import json, sys, time",
            # Drain the prompt first; a large prompt would otherwise block the
            # runner's stdin write and deadlock the caller.
            "sys.stdin.read()",
            "def emit(event):",
            "    sys.stdout.write(json.dumps(event) + chr(10))",
            "    sys.stdout.flush()",
            f"emit({{'type': 'thread.started', 'thread_id': {self.THREAD_ID!r}}})",
        ]
        if block_on is not None:
            body += [
                "import os.path",
                # Bounded so a failing test can never wedge the suite.
                "deadline = time.monotonic() + 30",
                f"while not os.path.exists({os.fspath(block_on)!r}):",
                "    if time.monotonic() > deadline:",
                "        break",
                "    time.sleep(0.05)",
            ]
        if verdict is not None:
            body.append(
                "emit({'type': 'item.completed', 'item': "
                f"{{'type': 'agent_message', 'text': {verdict!r}}}}})"
            )
        fake_codex.write_text("\n".join(body) + "\n", encoding="utf-8")
        fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
        return fake_codex

    def _run(self, root: Path, fake_codex: Path, session: str, *extra: str):
        return subprocess.run(
            [
                sys.executable,
                os.fspath(SCRIPT),
                "--session",
                session,
                "--new-session",
                "--question",
                "Review the background contract.",
                "--codex-bin",
                os.fspath(fake_codex),
                "--no-print-next-command",
                *extra,
            ],
            cwd=root,
            env={
                **os.environ,
                "CODEX_PEER_LOOP_STATE_DIR": os.fspath(root / "state"),
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

    def _announced_paths(self, banner: str) -> dict[str, Path]:
        labels = {
            "Artifact (written on completion): ": "artifact",
            "Status receipt (written on completion): ": "status",
            "Live stdout: ": "stdout",
            "Live stderr: ": "stderr",
        }
        found: dict[str, Path] = {}
        for line in banner.splitlines():
            for prefix, key in labels.items():
                if line.startswith(prefix):
                    found[key] = Path(line[len(prefix) :].strip())
        return found

    def _wait_for(self, predicate, timeout: float = 20.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return True
            except OSError:
                pass
            time.sleep(0.05)
        return False

    def test_banner_reaches_the_caller_while_codex_is_still_running(self) -> None:
        """The defining behavior: a caller can identify a run mid-flight."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            release = root / "release"
            fake_codex = self._write_fake_codex(
                root, verdict=self.GREEN, block_on=release
            )

            process = subprocess.Popen(
                [
                    sys.executable,
                    os.fspath(SCRIPT),
                    "--session",
                    "background-tracking-test",
                    "--new-session",
                    "--question",
                    "Review the background contract.",
                    "--codex-bin",
                    os.fspath(fake_codex),
                    "--no-print-next-command",
                ],
                cwd=root,
                env={
                    **os.environ,
                    "CODEX_PEER_LOOP_STATE_DIR": os.fspath(root / "state"),
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.addCleanup(process.kill)
            assert process.stdout is not None
            assert process.stderr is not None
            self.addCleanup(process.stdout.close)
            self.addCleanup(process.stderr.close)

            try:
                banner_lines: list[str] = []

                def read_banner() -> None:
                    assert process.stdout is not None
                    for line in process.stdout:
                        banner_lines.append(line)
                        if "this stream stays quiet" in line:
                            return

                # Read on a bounded thread: an unflushed banner would otherwise
                # arrive only at exit, hanging this test instead of failing it.
                reader = threading.Thread(target=read_banner, daemon=True)
                reader.start()
                reader.join(timeout=20)
                banner = "".join(banner_lines)

                self.assertFalse(
                    reader.is_alive(),
                    "banner never reached the caller while Codex was running; "
                    "the runner must flush it before waiting",
                )

                # Everything below is observed while Codex is still blocked.
                self.assertIsNone(
                    process.poll(), "runner exited before the banner could be used"
                )
                self.assertIn("background-tracking-test", banner)
                self.assertNotIn("VERDICT", banner)

                announced = self._announced_paths(banner)
                self.assertEqual(
                    sorted(announced),
                    ["artifact", "status", "stderr", "stdout"],
                    f"banner did not announce every path: {banner}",
                )
                # Sidecars must be readable the moment they are announced.
                self.assertTrue(announced["stdout"].exists())
                self.assertTrue(announced["stderr"].exists())
                self.assertFalse(announced["artifact"].exists())

                # Codex itself is up, not merely the runner: its first event
                # has landed in the announced sidecar while it stays blocked.
                self.assertTrue(
                    self._wait_for(
                        lambda: "thread.started" in announced["stdout"].read_text()
                    ),
                    "Codex never reached its blocking loop",
                )
                self.assertIsNone(process.poll())
            finally:
                release.write_text("go", encoding="utf-8")

            exit_code = process.wait(timeout=60)
            remaining_stdout = process.stdout.read()

            self.assertEqual(exit_code, 0, process.stderr.read())
            self.assertTrue(announced["artifact"].exists())
            self.assertIn("VERDICT: green", announced["artifact"].read_text())
            self.assertIn("VERDICT: green", remaining_stdout)

            # Every receipt field SKILL.md promotes to the success contract.
            status = announced["status"].read_text(encoding="utf-8")
            for field in (
                "exit_code=0",
                "timed_out=false",
                "thread_identity_status=passed",
                "green_light=true",
                "green_verdict=true",
                "min_score=10",
            ):
                self.assertIn(field, status)

    def test_non_green_gate_exit_and_receipt_agree_while_health_fields_show_codex_ran(
        self,
    ) -> None:
        """The receipt shares exit 2 while health fields show Codex ran."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_codex = self._write_fake_codex(root, verdict=self.NON_GREEN)
            completed = self._run(
                root,
                fake_codex,
                "non-green-receipt-test",
                "--require-green",
                "--required-min-score",
                "8",
            )

            self.assertEqual(completed.returncode, 2, completed.stderr)
            status_files = sorted((root / ".codex" / "artifacts").glob("*.status"))
            self.assertEqual(len(status_files), 1)
            status = status_files[0].read_text(encoding="utf-8")

        self.assertIn("exit_code=2", status)
        self.assertIn("timed_out=false", status)
        self.assertIn("thread_identity_status=passed", status)
        self.assertIn("green_light=false", status)
        self.assertIn("green_verdict=false", status)
        self.assertIn("min_score=5", status)

    def test_same_title_runs_never_share_artifact_paths(self) -> None:
        """Second-granular timestamps alone would collide under concurrency."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            args = SimpleNamespace(
                title="background execution contract",
                artifact_dir=None,
            )
            paths = {
                codex_peer_loop.new_artifact_path(root, args) for _ in range(25)
            }

        self.assertEqual(len(paths), 25)

    def test_artifact_directory_can_be_kept_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repo"
            external = Path(temporary_directory) / "review-artifacts"
            root.mkdir()
            args = SimpleNamespace(
                title="external artifact contract",
                artifact_dir=os.fspath(external),
            )

            artifact = codex_peer_loop.new_artifact_path(root, args)

            self.assertEqual(artifact.parent, external)


class ReliabilityUpgradeTests(unittest.TestCase):
    THREAD_ID = "0e13a9e2-58f6-4a70-9c7b-0f6e54a1c111"

    def _read_progress(self, path: Path) -> dict[str, str]:
        pairs = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            pairs[key] = value
        return pairs

    def _thread_event(self) -> str:
        return (
            json.dumps({"type": "thread.started", "thread_id": self.THREAD_ID})
            + "\n"
        )

    def test_progress_tracker_counts_events_and_persists_thread_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            progress_path = Path(temporary_directory) / "run.progress"
            seen: list[str] = []
            tracker = codex_peer_loop.ProgressTracker(
                progress_path, on_thread_id=seen.append
            )
            tracker.handle_line(self._thread_event())
            tracker.handle_line("not json\n")
            tracker.handle_line(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "command": "pytest -q",
                        },
                    }
                )
                + "\n"
            )
            tracker.handle_line(
                json.dumps(
                    {"type": "item.completed", "item": {"type": "file_change"}}
                )
                + "\n"
            )
            tracker.handle_line(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "all done"},
                    }
                )
                + "\n"
            )
            pairs = self._read_progress(progress_path)

        self.assertEqual(seen, [self.THREAD_ID])
        self.assertEqual(pairs["thread_id"], self.THREAD_ID)
        self.assertEqual(pairs["commands"], "1")
        self.assertEqual(pairs["file_changes"], "1")
        self.assertEqual(pairs["agent_messages"], "1")
        self.assertEqual(pairs["last_event"], "agent_message")

    def test_progress_tracker_reports_thread_id_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            seen: list[str] = []
            tracker = codex_peer_loop.ProgressTracker(
                Path(temporary_directory) / "run.progress",
                on_thread_id=seen.append,
            )
            tracker.handle_line(self._thread_event())
            tracker.handle_line(self._thread_event())

        self.assertEqual(seen, [self.THREAD_ID])

    def test_progress_tracker_ignores_non_uuid_thread_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            seen: list[str] = []
            tracker = codex_peer_loop.ProgressTracker(
                Path(temporary_directory) / "run.progress",
                on_thread_id=seen.append,
            )
            tracker.handle_line(
                json.dumps(
                    {"type": "thread.started", "thread_id": "not-a-uuid"}
                )
                + "\n"
            )

        self.assertEqual(seen, [])

    def test_progress_tracker_on_real_stream_shapes(self) -> None:
        events = [
            {"type": "thread.started", "thread_id": self.THREAD_ID},
            {"type": "turn.started"},
            {
                "type": "item.started",
                "item": {
                    "id": "item_2",
                    "type": "command_execution",
                    "command": "/bin/zsh -lc 'pytest -q'",
                    "aggregated_output": "",
                    "exit_code": None,
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "command_execution",
                    "command": "/bin/zsh -lc 'pytest -q'",
                    "aggregated_output": "25 passed",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_3",
                    "type": "agent_message",
                    "text": "the final report",
                },
            },
            {"type": "turn.completed", "usage": {"input_tokens": 1}},
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            progress_path = Path(temporary_directory) / "run.progress"
            tracker = codex_peer_loop.ProgressTracker(progress_path)
            for event in events:
                tracker.handle_line(json.dumps(event) + "\n")
            pairs = self._read_progress(progress_path)

        self.assertEqual(pairs["commands"], "1")
        self.assertEqual(pairs["agent_messages"], "1")
        self.assertEqual(pairs["thread_id"], self.THREAD_ID)
        self.assertEqual(tracker.thread_id, self.THREAD_ID)
        self.assertEqual(tracker.last_agent_message, "the final report")
        self.assertEqual(pairs["last_event"], "turn.completed")
        self.assertEqual(pairs["last_detail"], "the final report")

    def test_progress_tracker_records_persist_failure(self) -> None:
        def explode(_thread_id: str) -> None:
            raise OSError("disk full")

        with tempfile.TemporaryDirectory() as temporary_directory:
            progress_path = Path(temporary_directory) / "run.progress"
            tracker = codex_peer_loop.ProgressTracker(
                progress_path, on_thread_id=explode
            )
            tracker.handle_line(self._thread_event())
            pairs = self._read_progress(progress_path)

        self.assertTrue(pairs["thread_persist"].startswith("failed"))
        self.assertEqual(tracker.thread_id, self.THREAD_ID)

    def test_persist_at_exit_records_failure_without_raising(self) -> None:
        def explode(_thread_id: str) -> None:
            raise OSError("disk full")

        with tempfile.TemporaryDirectory() as temporary_directory:
            progress_path = Path(temporary_directory) / "run.progress"
            tracker = codex_peer_loop.ProgressTracker(
                progress_path, on_thread_id=explode
            )
            tracker.handle_line(self._thread_event())
            persisted = tracker.persist_at_exit(explode)
            pairs = self._read_progress(progress_path)

        self.assertFalse(persisted)
        self.assertTrue(pairs["thread_persist"].startswith("failed"))

    def test_persist_at_exit_retries_failed_live_store(self) -> None:
        def explode(_thread_id: str) -> None:
            raise OSError("disk full")

        with tempfile.TemporaryDirectory() as temporary_directory:
            stored: list[str] = []
            progress_path = Path(temporary_directory) / "run.progress"
            tracker = codex_peer_loop.ProgressTracker(
                progress_path, on_thread_id=explode
            )
            tracker.handle_line(self._thread_event())
            persisted = tracker.persist_at_exit(stored.append)
            pairs = self._read_progress(progress_path)

        self.assertTrue(persisted)
        self.assertEqual(stored, [self.THREAD_ID])
        self.assertEqual(pairs["thread_persist"], "ok")

    def test_persist_at_exit_without_thread_id_is_false(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            tracker = codex_peer_loop.ProgressTracker(
                Path(temporary_directory) / "run.progress"
            )

            self.assertFalse(tracker.persist_at_exit(lambda _thread_id: None))

    def test_persist_at_exit_waits_for_slow_live_persist(self) -> None:
        calls: list[tuple[str, str]] = []

        def slow_live(thread_id: str) -> None:
            time.sleep(0.2)
            calls.append(("live", thread_id))

        with tempfile.TemporaryDirectory() as temporary_directory:
            tracker = codex_peer_loop.ProgressTracker(
                Path(temporary_directory) / "run.progress",
                on_thread_id=slow_live,
            )
            drain = threading.Thread(
                target=tracker.handle_line, args=(self._thread_event(),)
            )
            drain.start()
            time.sleep(0.05)
            persisted = tracker.persist_at_exit(
                lambda thread_id: calls.append(("exit", thread_id))
            )
            drain.join()

        self.assertTrue(persisted)
        self.assertEqual(calls, [("live", self.THREAD_ID)])

    def test_tracker_without_callback_reports_na(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            progress_path = Path(temporary_directory) / "run.progress"
            tracker = codex_peer_loop.ProgressTracker(
                progress_path, on_thread_id=None
            )
            tracker.handle_line(self._thread_event())
            pairs = self._read_progress(progress_path)

        self.assertEqual(pairs["thread_persist"], "n/a")
        self.assertEqual(tracker.thread_id, self.THREAD_ID)

    def test_tail_buffer_bounds_many_lines_and_keeps_tail(self) -> None:
        buffer = codex_peer_loop.TailBuffer(100)
        for index in range(50):
            buffer.append(f"line-{index:04d}\n")

        self.assertLessEqual(len(buffer.text()), 100)
        self.assertTrue(buffer.text().endswith("line-0049\n"))

    def test_tail_buffer_bounds_single_huge_line(self) -> None:
        buffer = codex_peer_loop.TailBuffer(100)
        buffer.append("x" * 5000 + "END\n")

        self.assertLessEqual(len(buffer.text()), 100)
        self.assertTrue(buffer.text().endswith("END\n"))

    def test_run_codex_bounds_retained_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            original_limit = codex_peer_loop.RETAINED_STREAM_CHARS
            self.addCleanup(
                setattr,
                codex_peer_loop,
                "RETAINED_STREAM_CHARS",
                original_limit,
            )
            codex_peer_loop.RETAINED_STREAM_CHARS = 50_000
            code = (
                "import sys\n"
                "sys.stdout.write('y' * 120_000 + '\\n')\n"
                "sys.stdout.write('tail-marker\\n')\n"
            )
            (
                exit_code,
                stdout,
                _stderr,
                timed_out,
                drain_complete,
                _group_status,
            ) = codex_peer_loop.run_codex(
                [sys.executable, "-u", "-c", code],
                "prompt",
                30,
                root,
                root / "out.txt",
                root / "err.txt",
            )
            full_stdout = (root / "out.txt").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertFalse(timed_out)
        self.assertTrue(drain_complete)
        self.assertLessEqual(len(stdout), 50_000)
        self.assertTrue(stdout.endswith("tail-marker\n"))
        self.assertGreaterEqual(len(full_stdout), 120_000)

    def test_run_codex_timeout_still_streams_thread_event(self) -> None:
        code = (
            "import json, time\n"
            f"print(json.dumps({{'type': 'thread.started', 'thread_id': '{self.THREAD_ID}'}}), flush=True)\n"
            "time.sleep(30)\n"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            progress_path = root / "run.progress"
            seen: list[str] = []
            tracker = codex_peer_loop.ProgressTracker(
                progress_path, on_thread_id=seen.append
            )
            (
                exit_code,
                stdout,
                _stderr,
                timed_out,
                drain_complete,
                _group_status,
            ) = codex_peer_loop.run_codex(
                [sys.executable, "-u", "-c", code],
                "prompt",
                1,
                root,
                root / "out.txt",
                root / "err.txt",
                stdout_line_hook=tracker.handle_line,
            )
            pairs = self._read_progress(progress_path)

        self.assertTrue(timed_out)
        self.assertEqual(exit_code, 124)
        self.assertTrue(drain_complete)
        self.assertEqual(seen, [self.THREAD_ID])
        self.assertIn(self.THREAD_ID, stdout)
        self.assertEqual(pairs["thread_id"], self.THREAD_ID)

    def test_timeout_leaves_resumable_session_state(self) -> None:
        code = (
            "import json, time\n"
            f"print(json.dumps({{'type': 'thread.started', 'thread_id': '{self.THREAD_ID}'}}), flush=True)\n"
            "time.sleep(30)\n"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state_dir = root / "state"
            original_state_dir = codex_peer_loop.STATE_DIR
            self.addCleanup(setattr, codex_peer_loop, "STATE_DIR", original_state_dir)
            codex_peer_loop.STATE_DIR = state_dir
            tracker = codex_peer_loop.ProgressTracker(
                root / "run.progress",
                on_thread_id=lambda thread_id: codex_peer_loop.write_stored_thread_id(
                    "sess", thread_id, root
                ),
            )
            (
                _exit_code,
                _stdout,
                _stderr,
                timed_out,
                drain_complete,
                _group_status,
            ) = codex_peer_loop.run_codex(
                [sys.executable, "-u", "-c", code],
                "prompt",
                1,
                root,
                root / "out.txt",
                root / "err.txt",
                stdout_line_hook=tracker.handle_line,
            )
            stored = codex_peer_loop.read_stored_thread_id("sess", root)

        self.assertTrue(timed_out)
        self.assertTrue(drain_complete)
        self.assertEqual(stored, self.THREAD_ID)

    def test_write_stored_thread_id_atomic_and_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state_dir = root / "state"
            original_state_dir = codex_peer_loop.STATE_DIR
            self.addCleanup(setattr, codex_peer_loop, "STATE_DIR", original_state_dir)
            codex_peer_loop.STATE_DIR = state_dir
            codex_peer_loop.write_stored_thread_id(
                "sess", self.THREAD_ID, root
            )
            stored = codex_peer_loop.read_stored_thread_id("sess", root)
            leftovers = [path for path in state_dir.iterdir() if path.suffix == ".tmp"]

        self.assertEqual(stored, self.THREAD_ID)
        self.assertEqual(leftovers, [])

    def test_can_resume_by_name_truth_table(self) -> None:
        self.assertTrue(
            codex_peer_loop.can_resume_by_name("resume", thread_persisted=False)
        )
        self.assertTrue(
            codex_peer_loop.can_resume_by_name("new", thread_persisted=True)
        )
        self.assertFalse(
            codex_peer_loop.can_resume_by_name("new", thread_persisted=False)
        )
        self.assertFalse(
            codex_peer_loop.can_resume_by_name(
                "new (no stored session; fell back)", thread_persisted=False
            )
        )

    def test_new_session_invalidates_stale_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state_dir = root / "state"
            original_state_dir = codex_peer_loop.STATE_DIR
            self.addCleanup(setattr, codex_peer_loop, "STATE_DIR", original_state_dir)
            codex_peer_loop.STATE_DIR = state_dir
            stale = "9e13a9e2-58f6-4a70-9c7b-0f6e54a1c999"
            codex_peer_loop.write_stored_thread_id("sess", stale, root)
            codex_peer_loop.invalidate_stored_thread_id("sess", root)
            stored = codex_peer_loop.read_stored_thread_id("sess", root)
            codex_peer_loop.invalidate_stored_thread_id("sess", root)

        self.assertIsNone(stored)

    def test_write_stored_thread_id_cleans_tmp_on_failed_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state_dir = root / "state"
            original_state_dir = codex_peer_loop.STATE_DIR
            self.addCleanup(setattr, codex_peer_loop, "STATE_DIR", original_state_dir)
            codex_peer_loop.STATE_DIR = state_dir
            with mock.patch.object(
                codex_peer_loop.os,
                "replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaises(OSError):
                    codex_peer_loop.write_stored_thread_id(
                        "sess", self.THREAD_ID, root
                    )
            leftovers = list(state_dir.glob("*.tmp"))

        self.assertEqual(leftovers, [])

    def test_tail_buffer_is_safe_under_concurrent_append(self) -> None:
        buffer = codex_peer_loop.TailBuffer(10_000)
        stop = threading.Event()

        def writer() -> None:
            index = 0
            while not stop.is_set():
                buffer.append(f"line-{index}\n")
                index += 1

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            for _ in range(200):
                text = buffer.text()
                self.assertLessEqual(len(text), 10_000)
        finally:
            stop.set()
            thread.join()

    def test_run_codex_blocked_hook_reports_drain_incomplete_promptly(self) -> None:
        had_join_seconds = hasattr(codex_peer_loop, "DRAIN_JOIN_SECONDS")
        original_join_seconds = getattr(
            codex_peer_loop, "DRAIN_JOIN_SECONDS", None
        )
        codex_peer_loop.DRAIN_JOIN_SECONDS = 0.3
        release = threading.Event()
        hook_finished = threading.Event()

        def blocking_store(_thread_id: str) -> None:
            release.wait(10)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            tracker = codex_peer_loop.ProgressTracker(
                root / "run.progress", on_thread_id=blocking_store
            )

            def handle_line(line: str) -> None:
                try:
                    tracker.handle_line(line)
                finally:
                    hook_finished.set()

            code = (
                "import json\n"
                f"print(json.dumps({{'type': 'thread.started', 'thread_id': '{self.THREAD_ID}'}}), flush=True)\n"
            )
            started = time.monotonic()
            try:
                (
                    exit_code,
                    _stdout,
                    stderr,
                    timed_out,
                    drain_complete,
                    _group_status,
                ) = codex_peer_loop.run_codex(
                    [sys.executable, "-u", "-c", code],
                    "prompt",
                    30,
                    root,
                    root / "out.txt",
                    root / "err.txt",
                    stdout_line_hook=handle_line,
                )
                elapsed = time.monotonic() - started
                self.assertEqual(exit_code, 0)
                self.assertFalse(timed_out)
                self.assertFalse(drain_complete)
                self.assertLess(elapsed, 5)
                self.assertIn("may all be incomplete", stderr)
            finally:
                release.set()
                self.assertTrue(hook_finished.wait(5))
                if had_join_seconds:
                    codex_peer_loop.DRAIN_JOIN_SECONDS = original_join_seconds
                else:
                    del codex_peer_loop.DRAIN_JOIN_SECONDS


class CommandConstructionTests(unittest.TestCase):
    def test_dry_run_does_not_mutate_cached_last_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state_dir = root / "state"
            state_dir.mkdir()
            state_key = codex_peer_loop.scoped_session_key("dry-run-test", root)
            last_file = state_dir / f"{state_key}.last.txt"
            last_file.write_text("preserve me", encoding="utf-8")
            fake_codex = root / "codex"
            fake_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            result = subprocess.run(
                [
                    sys.executable,
                    os.fspath(SCRIPT),
                    "--session",
                    "dry-run-test",
                    "--question",
                    "Inspect the prompt.",
                    "--codex-bin",
                    os.fspath(fake_codex),
                    "--dry-run",
                    "--no-print-next-command",
                ],
                cwd=root,
                env={
                    **os.environ,
                    "CODEX_PEER_LOOP_STATE_DIR": os.fspath(state_dir),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            cached_text = last_file.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cached_text, "preserve me")

    def test_resume_reasserts_model_and_effort(self) -> None:
        arguments = SimpleNamespace(
            codex_bin="/path/to/codex",
            model="gpt-6-astra",
            effort="xhigh",
            fast=False,
            disable_mcp=True,
        )

        command = codex_peer_loop.resume_command(
            arguments,
            Path("/tmp/codex-peer-last-message.txt"),
            "019f67c6-f255-7751-9af1-23a141fd729b",
        )

        self.assertIn("gpt-6-astra", command)
        self.assertIn("model_reasoning_effort=xhigh", command)
        self.assertIn("mcp_servers={}", command)

    def test_resume_skeleton_preserves_environment_selected_settings(self) -> None:
        args = codex_peer_loop.parse_args(
            [
                "--question",
                "Review this change.",
                "--session",
                "continuity-test",
                "--title",
                "continuity",
                "--skepticism",
                "blocking",
                "--timeout-seconds",
                "4200",
                "--context-bytes",
                "1234",
                "--context-total-bytes",
                "5678",
                "--artifact-dir",
                "/tmp/codex-peer-loop-artifacts",
            ],
            environ={
                "CODEX_PEER_LOOP_MODEL": "gpt-5.6-terra",
                "CODEX_PEER_LOOP_EFFORT": "xhigh",
            },
        )
        args.codex_bin = "/path/to/codex"

        resume_tokens = shlex.split(codex_peer_loop.next_command(args))
        resumed = codex_peer_loop.parse_args(resume_tokens[1:], environ={})

        self.assertEqual(resumed.model, args.model)
        self.assertEqual(resumed.effort, args.effort)
        self.assertEqual(resumed.skepticism, args.skepticism)
        self.assertEqual(resumed.timeout_seconds, args.timeout_seconds)
        self.assertEqual(resumed.context_bytes, args.context_bytes)
        self.assertEqual(resumed.context_total_bytes, args.context_total_bytes)
        self.assertEqual(resumed.artifact_dir, args.artifact_dir)

    def test_resume_skeleton_serializes_default_runtime_settings(self) -> None:
        args = codex_peer_loop.parse_args(
            ["--question", "Review this change."],
            environ={},
        )
        args.codex_bin = "/path/to/codex"

        resume_tokens = shlex.split(codex_peer_loop.next_command(args))

        self.assertIn("--model", resume_tokens)
        self.assertIn("--effort", resume_tokens)
        self.assertIn("--timeout-seconds", resume_tokens)
        self.assertIn("--context-bytes", resume_tokens)
        self.assertIn("--context-total-bytes", resume_tokens)

    def test_resume_keeps_title_stable(self) -> None:
        args = codex_peer_loop.parse_args(
            [
                "--question",
                "Review this change.",
                "--title",
                "design-review",
                "--iteration",
                "2",
            ],
            environ={},
        )
        args.codex_bin = "/path/to/codex"

        resume_tokens = shlex.split(codex_peer_loop.next_command(args))
        resumed = codex_peer_loop.parse_args(resume_tokens[1:], environ={})

        self.assertEqual(resumed.title, "design-review")


class ContextBudgetTests(unittest.TestCase):
    def test_rejects_non_positive_excerpt_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            context_file = Path(temporary_directory) / "context.txt"
            context_file.write_text("bounded context", encoding="utf-8")

            with self.assertRaises(ValueError):
                codex_peer_loop.read_file_excerpt(os.fspath(context_file), 0)

    def test_excerpt_is_truncated_at_byte_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            context_file = Path(temporary_directory) / "context.txt"
            context_file.write_bytes(b"x" * 10_000)

            excerpt = codex_peer_loop.read_file_excerpt(
                os.fspath(context_file),
                128,
            )

        self.assertTrue(excerpt.startswith("x" * 128))
        self.assertNotIn("x" * 129, excerpt)
        self.assertIn("[truncated after 128 bytes]", excerpt)


class PromptQualityTests(unittest.TestCase):
    def test_full_prompt_is_bounded_and_challenges_overengineering(self) -> None:
        args = codex_peer_loop.parse_args(
            [
                "--question",
                "Review this change.",
                "--phase",
                "commit-gate",
                "--no-include-git-summary",
            ],
            environ={},
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            prompt = codex_peer_loop.build_prompt(
                args,
                "",
                Path(temporary_directory),
            )

        self.assertLessEqual(len(prompt.split()), 600)
        for term in (
            "overengineering",
            "overcomplication",
            "maintainability",
            "delete",
            "reuse",
            "assumptions",
            "unknowns",
        ):
            with self.subTest(term=term):
                self.assertIn(term, prompt.lower())
        self.assertIn("first three", prompt.lower())
        response_section = prompt.rsplit("Required response format", maxsplit=1)[1]
        self.assertLess(
            response_section.index("VERDICT:"),
            response_section.index("GREEN_LIGHT:"),
        )
        self.assertLess(
            response_section.index("GREEN_LIGHT:"),
            response_section.index("MIN_SCORE:"),
        )



class ReviewPolicyTests(unittest.TestCase):
    """Session settings, gate policy, pass budget, and the review manifest,
    exercised through the CLI against a stand-in Codex."""

    THREAD_ID = "019f9532-bc8d-7410-b6cc-3941d027574a"
    GREEN_LOW_SCORE = "VERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 5"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.state = self.root.parent / f"{self.root.name}-state"
        self.addCleanup(shutil.rmtree, self.state, True)
        self.addCleanup(self._tmp.cleanup)

    def fake_codex(self, verdict: str, touch: Path | None = None) -> Path:
        fake = self.root.parent / f"{self.root.name}-codex"
        lines = [
            f"#!{sys.executable}",
            "import json, sys",
            "sys.stdin.read()",
            "def emit(event):",
            "    sys.stdout.write(json.dumps(event) + chr(10))",
            "    sys.stdout.flush()",
            f"emit({{'type': 'thread.started', 'thread_id': {self.THREAD_ID!r}}})",
        ]
        if touch is not None:
            lines.append(f"open({os.fspath(touch)!r}, 'a').write('changed during review')")
        lines.append(
            "emit({'type': 'item.completed', 'item': "
            f"{{'type': 'agent_message', 'text': {verdict!r}}}}})"
        )
        fake.write_text("\n".join(lines) + "\n", encoding="utf-8")
        fake.chmod(0o755)
        self.addCleanup(fake.unlink, True)
        return fake

    def run_cli(self, fake: Path, *flags: str, env: dict[str, str] | None = None):
        return subprocess.run(
            [
                sys.executable,
                os.fspath(SCRIPT),
                "--session",
                "policy",
                "--question",
                "Review the change.",
                "--codex-bin",
                os.fspath(fake),
                *flags,
            ],
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            env={
                **os.environ,
                "CODEX_PEER_LOOP_STATE_DIR": os.fspath(self.state),
                **(env or {}),
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

    def run_pass(self, fake: Path, *flags: str, env: dict[str, str] | None = None):
        completed = self.run_cli(fake, *flags, env=env)
        artifact = next(
            line.split("Artifact saved to ", 1)[1].strip()
            for line in completed.stdout.splitlines()
            if line.startswith("Artifact saved to ")
        )
        status_text = Path(artifact).with_suffix(".status").read_text(encoding="utf-8")
        status = dict(line.split("=", 1) for line in status_text.splitlines())
        return completed, status

    def test_a_resumed_session_keeps_its_settings_without_repeating_flags(self) -> None:
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        _, first = self.run_pass(
            fake, "--new-session", "--phase", "plan", "--complexity", "complex", "--model", "gpt-chosen"
        )
        self.assertEqual((first["model"], first["effort"]), ("gpt-chosen", "xhigh"))

        # Environment defaults only apply to new sessions.
        drifted_env = {
            "CODEX_PEER_LOOP_MODEL": "gpt-other",
            "CODEX_PEER_LOOP_COMPLEXITY": "trivial",
        }
        _, resumed = self.run_pass(fake, "--phase", "verification", env=drifted_env)
        self.assertEqual(resumed["command_kind"], "resume")
        self.assertEqual(resumed["model"], "gpt-chosen")
        self.assertEqual(resumed["complexity"], "complex")
        self.assertEqual(resumed["effort_requested"], "auto")
        self.assertEqual(resumed["effort"], "high")

        # An explicit flag wins and becomes the session's new setting.
        _, lowered = self.run_pass(fake, "--phase", "verification", "--complexity", "routine")
        self.assertEqual(lowered["effort"], "medium")
        _, kept = self.run_pass(fake, "--phase", "verification")
        self.assertEqual(kept["complexity"], "routine")

    def test_a_pinned_effort_stays_pinned_across_resumes(self) -> None:
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        self.run_pass(fake, "--new-session", "--phase", "plan", "--effort", "low")
        _, resumed = self.run_pass(fake, "--phase", "commit-gate")
        self.assertEqual((resumed["effort_requested"], resumed["effort"]), ("low", "low"))

    def test_min_score_is_advisory_unless_a_minimum_is_requested(self) -> None:
        self.assertIsNone(codex_peer_loop.green_gate_failure(self.GREEN_LOW_SCORE))
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        advisory, status = self.run_pass(fake, "--new-session", "--require-green")
        self.assertEqual(advisory.returncode, 0, advisory.stderr)
        self.assertEqual(status["required_min_score"], "advisory")
        enforced, _ = self.run_pass(
            fake, "--new-session", "--require-green", "--required-min-score", "8"
        )
        self.assertEqual(enforced.returncode, 2)

    def test_spent_gate_budget_stops_suggesting_another_model_pass(self) -> None:
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        outputs = [
            self.run_pass(fake, "--new-session", "--phase", "commit-gate")[0].stdout,
            self.run_pass(fake, "--phase", "verification")[0].stdout,
            self.run_pass(fake, "--phase", "verification")[0].stdout,
        ]
        for suggested in outputs[:2]:
            self.assertIn("Next resume command skeleton", suggested)
            self.assertNotIn("Pass budget spent", suggested)
        self.assertNotIn("Next resume command skeleton", outputs[2])
        self.assertIn("Pass budget spent", outputs[2])
        self.assertIn("never approves the change", outputs[2])

    def test_pass_budget_families(self) -> None:
        spent = codex_peer_loop.spent_pass_budget

        def passes(*phases: str) -> list[dict[str, object]]:
            return [{"phase": phase} for phase in phases]

        self.assertIsNone(spent(passes("plan")))
        self.assertEqual(spent(passes("plan", "verification")), "design")
        # The first code gate after a plan starts the gate budget.
        self.assertIsNone(spent(passes("plan", "commit-gate", "verification")))
        self.assertEqual(
            spent(passes("plan", "commit-gate", "verification", "verification")), "gate"
        )
        # Re-running a full gate does not reset the budget.
        self.assertEqual(spent(passes("commit-gate", "verification", "commit-gate")), "gate")
        self.assertIsNone(spent(passes("review", "review", "review")))

    def test_pass_mission_follows_the_phase_not_the_iteration(self) -> None:
        def prompt(*flags: str) -> str:
            args = codex_peer_loop.parse_args(
                ["--question", "q", "--no-include-git-summary", *flags], environ={}
            )
            return codex_peer_loop.build_prompt(args, "", self.root)

        first_gate = prompt("--phase", "commit-gate", "--iteration", "2")
        self.assertIn("fully review the whole current change", first_gate)
        self.assertNotIn("follow-up pass", first_gate)
        self.assertNotIn("## Prior Findings", first_gate)
        follow_up = prompt("--phase", "verification", "--iteration", "2")
        self.assertIn("follow-up pass", follow_up)
        self.assertIn("## Prior Findings", follow_up)
        self.assertIn("settle each prior finding by ID", follow_up)
        for text in (first_gate, follow_up):
            self.assertIn("stable ID (F1", text)
            self.assertIn("Blocker rule", text)
            self.assertIn("MIN_SCORE is diagnostic", text)

    def _git_repo(self) -> Path:
        if not shutil.which("git"):
            self.skipTest("git not available")
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run([*git, "init", "-q"], cwd=self.root, check=True)
        source = self.root / "src"
        source.mkdir()
        (source / "module.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run([*git, "add", "-A"], cwd=self.root, check=True)
        subprocess.run([*git, "commit", "-q", "-m", "init"], cwd=self.root, check=True)
        return source

    def test_manifest_records_what_was_reviewed(self) -> None:
        source = self._git_repo()
        (source / "module.py").write_text("x = 2\n", encoding="utf-8")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True, check=True
        ).stdout.strip()
        fake = self.fake_codex(self.GREEN_LOW_SCORE)

        completed, status = self.run_pass(
            fake, "--new-session", "--require-green", "--path", "src"
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(status["reviewed_head"], head)
        self.assertRegex(status["reviewed_worktree_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(status["content_drift"], "false")

    def test_content_changed_during_the_pass_is_not_green(self) -> None:
        source = self._git_repo()
        fake = self.fake_codex(self.GREEN_LOW_SCORE, touch=source / "module.py")

        completed, status = self.run_pass(
            fake, "--new-session", "--require-green", "--path", "src"
        )

        self.assertEqual(status["content_drift"], "true")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("changed during the run", completed.stderr)

    def test_a_failed_snapshot_is_never_certified_as_stable(self) -> None:
        self._git_repo()
        (self.root / ".git" / "index").write_bytes(b"corrupt index")
        fake = self.fake_codex(self.GREEN_LOW_SCORE)

        completed, status = self.run_pass(
            fake, "--new-session", "--require-green", "--path", "src"
        )

        self.assertNotEqual(status["manifest_error"], "")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("manifest", completed.stderr.lower())

    def test_context_read_for_the_prompt_is_inside_the_drift_check(self) -> None:
        brief = self.root / "brief.md"
        brief.write_text("requirement: old\n", encoding="utf-8")
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        real_build_prompt = codex_peer_loop.build_prompt

        def build_then_change(*args, **kwargs):
            prompt = real_build_prompt(*args, **kwargs)
            brief.write_text("requirement: new\n", encoding="utf-8")
            return prompt

        argv = [
            "codex_peer_loop.py", "--session", "ctx", "--new-session", "--require-green",
            "--question", "q", "--codex-bin", os.fspath(fake),
            "--context-file", os.fspath(brief), "--no-print-next-command",
        ]
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(codex_peer_loop, "STATE_DIR", self.state),
                mock.patch.object(codex_peer_loop, "read_stdin", return_value=""),
                mock.patch.object(codex_peer_loop, "build_prompt", side_effect=build_then_change),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                exit_code = codex_peer_loop.main()
        finally:
            os.chdir(cwd)

        status_file = next((self.root / ".codex" / "artifacts").glob("*.status"))
        self.assertIn("content_drift=true", status_file.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 2)

    def test_a_context_file_cut_at_the_per_file_cap_is_reported(self) -> None:
        brief = self.root / "brief.md"
        brief.write_bytes(b"x" * 10_000)
        fake = self.fake_codex(self.GREEN_LOW_SCORE)

        completed, status = self.run_pass(
            fake, "--new-session", "--context-file", os.fspath(brief), "--context-bytes", "128"
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            f"context_truncated: {brief} included=128 size=10000 bytes "
            "(raise --context-bytes / --context-total-bytes)",
            completed.stderr,
        )
        self.assertEqual(status["context_truncated"], "1")

    def test_a_context_file_left_out_by_the_total_budget_is_reported(self) -> None:
        whole = self.root / "whole.md"
        whole.write_bytes(b"x" * 128)
        left_out = self.root / "left-out.md"
        left_out.write_bytes(b"y" * 500)
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        flags = (
            "--context-file", os.fspath(whole), "--context-file", os.fspath(left_out),
            "--context-total-bytes", "128",
        )

        dry_run = self.run_cli(fake, "--new-session", "--dry-run", *flags)
        completed, status = self.run_pass(fake, "--new-session", *flags)

        expected = f"context_omitted: {left_out} size=500 bytes (total budget 128 spent)"
        for stderr in (dry_run.stderr, completed.stderr):
            self.assertIn(expected, stderr)
            self.assertNotIn(os.fspath(whole), stderr)
        self.assertEqual(status["context_truncated"], "1")

    def test_context_that_fits_is_not_reported(self) -> None:
        brief = self.root / "brief.md"
        brief.write_text("requirement: small\n", encoding="utf-8")
        fake = self.fake_codex(self.GREEN_LOW_SCORE)

        completed, status = self.run_pass(fake, "--new-session", "--context-file", os.fspath(brief))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("context_", completed.stderr)
        self.assertEqual(status["context_truncated"], "0")

    def test_a_failed_codex_launch_does_not_spend_the_pass_budget(self) -> None:
        good = self.fake_codex(self.GREEN_LOW_SCORE)
        self.run_pass(good, "--new-session", "--phase", "commit-gate")
        self.run_pass(good, "--phase", "verification")
        broken = self.root.parent / f"{self.root.name}-broken"
        broken.write_text(f"#!{sys.executable}\nimport sys\nsys.exit(2)\n", encoding="utf-8")
        broken.chmod(0o755)
        self.addCleanup(broken.unlink, True)

        failed, _ = self.run_pass(broken, "--phase", "verification")

        self.assertEqual(failed.returncode, 2)
        self.assertNotIn("Pass budget spent", failed.stdout)

    def test_history_write_failure_keeps_receipt_and_exit_in_agreement(self) -> None:
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        # Codex replaces the session state file with a directory mid-run, so
        # the post-run history write fails.
        sabotage = self.root.parent / f"{self.root.name}-sabotage"
        sabotage.write_text(
            f"#!{sys.executable}\n"
            "import glob, os, subprocess, sys\n"
            f"for path in glob.glob(os.path.join({os.fspath(self.state)!r}, '*.session.json')):\n"
            "    os.remove(path); os.mkdir(path)\n"
            f"sys.exit(subprocess.run([{os.fspath(fake)!r}], stdin=sys.stdin).returncode)\n",
            encoding="utf-8",
        )
        sabotage.chmod(0o755)
        self.addCleanup(sabotage.unlink, True)

        completed, status = self.run_pass(sabotage, "--new-session")

        self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual(completed.returncode, int(status["exit_code"]))
        self.assertTrue(status["pass_history"].startswith("failed"))

    def test_an_overridden_invalid_environment_default_is_ignored(self) -> None:
        environ = {
            "CODEX_PEER_LOOP_EFFORT": "bogus",
            "CODEX_PEER_LOOP_COMPLEXITY": "bogus",
        }
        args = codex_peer_loop.parse_args(
            ["--question", "q", "--effort", "high", "--complexity", "routine"],
            environ=environ,
        )
        codex_peer_loop.apply_session_settings(args)
        self.assertEqual(args.effort, "high")
        unresolved = codex_peer_loop.parse_args(["--question", "q"], environ=environ)
        with self.assertRaises(SystemExit) as raised:
            codex_peer_loop.apply_session_settings(unresolved)
        self.assertIn("CODEX_PEER_LOOP_EFFORT", str(raised.exception))

    def test_saved_settings_beat_an_invalid_environment_default_on_resume(self) -> None:
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        self.run_pass(fake, "--new-session", "--effort", "high", "--complexity", "routine")
        broken_env = {"CODEX_PEER_LOOP_EFFORT": "bogus", "CODEX_PEER_LOOP_COMPLEXITY": "bogus"}

        resumed, status = self.run_pass(fake, "--phase", "verification", env=broken_env)

        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual((status["effort"], status["complexity"]), ("high", "routine"))

    def _failing_git(self, failing_args: tuple[str, ...]) -> dict[str, str]:
        """PATH with a git that fails one probe the way an unsafe repo does."""
        real_git = shutil.which("git")
        assert real_git is not None
        bin_dir = self.root.parent / f"{self.root.name}-bin"
        bin_dir.mkdir()
        self.addCleanup(shutil.rmtree, bin_dir, True)
        wrapper = bin_dir / "git"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import os, sys\n"
            f"if tuple(sys.argv[1:{1 + len(failing_args)}]) == {failing_args!r}:\n"
            "    sys.stderr.write('fatal: detected dubious ownership in repository\\n')\n"
            "    sys.exit(128)\n"
            f"os.execv({real_git!r}, [{real_git!r}, *sys.argv[1:]])\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        return {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    def test_a_failed_repository_probe_is_never_certified_as_stable(self) -> None:
        self._git_repo()
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        for probe in (("rev-parse", "--is-inside-work-tree"), ("rev-parse", "-q", "--verify")):
            with self.subTest(probe=probe):
                env = self._failing_git(probe)
                completed, status = self.run_pass(
                    fake, "--new-session", "--require-green", "--path", "src", env=env
                )
                shutil.rmtree(self.root.parent / f"{self.root.name}-bin")
                self.assertNotEqual(status["manifest_error"], "")
                self.assertEqual(completed.returncode, 2)

    def test_only_a_missing_git_binary_counts_as_outside_git(self) -> None:
        self._git_repo()
        for failure, is_error in (
            (FileNotFoundError(2, "No such file", "git"), False),
            (PermissionError(13, "Permission denied", "git"), True),
            (OSError(24, "Too many open files"), True),
        ):
            with self.subTest(failure=type(failure).__name__):
                with mock.patch.object(codex_peer_loop.subprocess, "run", side_effect=failure):
                    manifest = codex_peer_loop.review_manifest(self.root, [], [], [])
                self.assertEqual(bool(manifest.get("error")), is_error, manifest)

    def test_outside_git_the_manifest_is_not_an_error(self) -> None:
        fake = self.fake_codex(self.GREEN_LOW_SCORE)
        completed, status = self.run_pass(fake, "--new-session", "--require-green")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(status["manifest_error"], "")

    def test_separate_git_dirs_get_distinct_session_scopes(self) -> None:
        if not shutil.which("git"):
            self.skipTest("git not available")
        scopes = []
        (self.root / "gitdirs").mkdir()
        for name in ("a", "b"):
            work = self.root / name
            work.mkdir()
            subprocess.run(
                ["git", "init", "-q", "--separate-git-dir", os.fspath(self.root / "gitdirs" / name)],
                cwd=work,
                check=True,
            )
            scopes.append(codex_peer_loop.session_scope_root(work))
        self.assertNotEqual(scopes[0], scopes[1])


if __name__ == "__main__":
    unittest.main()
