"""Process-lifecycle contract shared by codex-peer-loop and codex-implement-loop.

This file is byte-identical in both skills and exercises whichever runner sits
in ../scripts, so a lifecycle fix is proven against both implementations.
Every scenario drives a real stand-in `codex` executable.
"""

from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = next((Path(__file__).parents[1] / "scripts").glob("codex_*_loop.py"))
SPEC = importlib.util.spec_from_file_location(f"{SCRIPT.stem}_lifecycle", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)

PEER = SCRIPT.stem == "codex_peer_loop"
STATE_ENV = "CODEX_PEER_LOOP_STATE_DIR" if PEER else "CODEX_IMPLEMENT_LOOP_STATE_DIR"
BRIEF_FLAG = "--question" if PEER else "--task"
GATE_FLAGS = ["--require-green"] if PEER else []
SUCCESS = (
    "VERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 9"
    if PEER
    else "STATUS: done\nTESTS: pass"
)
FAILURE = (
    "VERDICT: blocked\nGREEN_LIGHT: no\nMIN_SCORE: 2"
    if PEER
    else "STATUS: blocked\nTESTS: fail"
)
THREAD_ID = "019f9532-bc8d-7410-b6cc-3941d027574a"

FAKE_PREAMBLE = f"""#!{sys.executable}
import json, os, pathlib, signal, subprocess, sys, time

def emit_raw(data):
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()

def emit(event):
    emit_raw((json.dumps(event) + "\\n").encode())

def message(text):
    emit({{"type": "item.completed", "item": {{"type": "agent_message", "text": text}}}})

def thread_started():
    emit({{"type": "thread.started", "thread_id": {THREAD_ID!r}}})

def last_message_path():
    return pathlib.Path(sys.argv[sys.argv.index("--output-last-message") + 1])

def wait_for(path, limit=30):
    deadline = time.monotonic() + limit
    while not os.path.exists(path) and time.monotonic() < deadline:
        time.sleep(0.02)

def spawn_stubborn_child(pid_file, beat_file):
    code = (
        "import signal, time, pathlib\\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\\n"
        f"beat = pathlib.Path({{beat_file!r}})\\n"
        "while True:\\n"
        "    with beat.open('a') as handle:\\n"
        "        handle.write('.')\\n"
        "    time.sleep(0.05)\\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pathlib.Path(pid_file).write_text(str(child.pid))
    wait_for(beat_file)
"""


def write_fake_codex(directory: Path, body: str) -> Path:
    path = directory / "codex"
    path.write_text(FAKE_PREAMBLE + textwrap.dedent(body), encoding="utf-8")
    path.chmod(0o755)
    return path


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_until_dead(pid: int, limit: float = 5.0) -> bool:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    return not pid_alive(pid)


class LifecycleCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.stdout_path = self.root / "run.stdout.txt"
        self.stderr_path = self.root / "run.stderr.txt"
        self.stdout_path.write_text("", encoding="utf-8")
        self.stderr_path.write_text("", encoding="utf-8")
        self._leftover_pids: list[int] = []

    def tearDown(self) -> None:
        for pid in self._leftover_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self._tmp.cleanup()

    def track_child(self, pid_file: Path) -> int:
        deadline = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        pid = int(pid_file.read_text())
        self._leftover_pids.append(pid)
        return pid

    def run_codex(self, fake: Path, timeout: int = 30, prompt: str = "brief"):
        return runner.run_codex(
            [os.fspath(fake), "--output-last-message", os.fspath(self.root / "last.txt")],
            prompt,
            timeout,
            self.root,
            self.stdout_path,
            self.stderr_path,
        )

    def run_cli(self, fake: Path, session: str, *extra: str, **popen) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.cli_command(fake, session, *extra),
            cwd=self.root,
            env=self.cli_env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            **popen,
        )

    def cli_command(self, fake: Path, session: str, *extra: str) -> list[str]:
        return [
            sys.executable,
            os.fspath(SCRIPT),
            "--session",
            session,
            "--new-session",
            BRIEF_FLAG,
            "Exercise the lifecycle contract.",
            "--codex-bin",
            os.fspath(fake),
            "--no-print-next-command",
            *GATE_FLAGS,
            *extra,
        ]

    def cli_env(self) -> dict[str, str]:
        return {**os.environ, STATE_ENV: os.fspath(self.root / "state")}

    def status_of(self, stdout: str) -> dict[str, str]:
        artifact = next(
            line.split("Artifact saved to ", 1)[1].strip()
            for line in stdout.splitlines()
            if line.startswith("Artifact saved to ")
        )
        status = Path(artifact).with_suffix(".status").read_text(encoding="utf-8")
        return dict(line.split("=", 1) for line in status.splitlines() if "=" in line)


class OutputCollectionTests(LifecycleCase):
    def test_undecodable_output_makes_the_run_incomplete_without_losing_later_lines(self) -> None:
        fake = write_fake_codex(
            self.root,
            f"""
            sys.stdin.read()
            thread_started()
            message({SUCCESS!r})
            emit_raw(b"\\xff\\xfe not utf-8\\n")
            message({FAILURE!r})
            """,
        )

        result = self.run_codex(fake)

        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.drain_complete)
        self.assertIn(FAILURE.splitlines()[0], self.stdout_path.read_text(encoding="utf-8"))

    def test_cli_never_reports_success_when_output_collection_failed(self) -> None:
        fake = write_fake_codex(
            self.root,
            f"""
            sys.stdin.read()
            thread_started()
            message({SUCCESS!r})
            emit_raw(b"\\xff\\xfe not utf-8\\n")
            message({FAILURE!r})
            """,
        )

        completed = self.run_cli(fake, "drain")

        self.assertEqual(completed.returncode, 5, completed.stderr)
        self.assertEqual(self.status_of(completed.stdout)["drain_complete"], "false")


class ProcessGroupTests(LifecycleCase):
    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(runner, "GROUP_TERM_GRACE_SECONDS", 0.5)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_timeout_stops_group_members_that_ignore_sigterm(self) -> None:
        pid_file = self.root / "child.pid"
        fake = write_fake_codex(
            self.root,
            f"""
            sys.stdin.read()
            thread_started()
            spawn_stubborn_child({os.fspath(pid_file)!r}, {os.fspath(self.root / "beat")!r})
            time.sleep(60)
            """,
        )

        result = self.run_codex(fake, timeout=2)
        child = self.track_child(pid_file)

        self.assertTrue(result.timed_out)
        self.assertEqual(result.exit_code, 124)
        self.assertEqual(result.group_status, "terminated")
        self.assertTrue(wait_until_dead(child), "child kept running after the timeout")

    def test_leftover_group_members_are_stopped_after_a_normal_exit(self) -> None:
        pid_file = self.root / "child.pid"
        fake = write_fake_codex(
            self.root,
            f"""
            sys.stdin.read()
            thread_started()
            spawn_stubborn_child({os.fspath(pid_file)!r}, {os.fspath(self.root / "beat")!r})
            message({SUCCESS!r})
            """,
        )

        result = self.run_codex(fake)
        child = self.track_child(pid_file)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.group_status, "terminated")
        self.assertTrue(wait_until_dead(child), "leftover child kept running")

    def test_a_clean_exit_reports_a_clean_group(self) -> None:
        fake = write_fake_codex(
            self.root,
            f"""
            sys.stdin.read()
            thread_started()
            message({SUCCESS!r})
            """,
        )

        result = self.run_codex(fake)

        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.drain_complete)
        self.assertEqual(result.group_status, "clean")


class PromptFeedingTests(LifecycleCase):
    def test_timeout_covers_a_codex_that_never_reads_its_prompt(self) -> None:
        fake = write_fake_codex(
            self.root,
            """
            thread_started()
            time.sleep(8)
            """,
        )
        started = time.monotonic()

        result = self.run_codex(fake, timeout=1, prompt="x" * 4_000_000)

        self.assertTrue(result.timed_out)
        self.assertLess(time.monotonic() - started, 6)


class BriefInputTests(LifecycleCase):
    """stdin is the brief only when the brief flag is absent; it is never
    guessed at, cut off, or silently dropped."""

    def launch(self, fake: Path, *, with_flag: bool, extra: tuple[str, ...] = ()) -> subprocess.Popen:
        command = self.cli_command(fake, "brief", *extra)
        if not with_flag:
            command = [part for part in command if part not in (
                BRIEF_FLAG, "Exercise the lifecycle contract."
            )]
        return subprocess.Popen(
            command, cwd=self.root, env=self.cli_env(), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def finish(self, process: subprocess.Popen) -> tuple[str, str]:
        try:
            return process.communicate(timeout=60)
        finally:
            if process.poll() is None:
                process.kill()

    def test_a_slow_piped_brief_is_read_in_full(self) -> None:
        fake = write_fake_codex(self.root, "sys.exit(0)\n")
        process = self.launch(fake, with_flag=False, extra=("--dry-run",))
        assert process.stdin is not None
        time.sleep(2.5)  # longer than any readiness guess
        process.stdin.write("Do not change the public API.\n")
        out, errors = self.finish(process)  # communicate() sends EOF

        self.assertEqual(process.returncode, 0, errors)
        self.assertIn("Do not change the public API.", out)

    def test_data_on_stdin_alongside_the_brief_flag_fails_loudly(self) -> None:
        launched = self.root / "launched"
        fake = write_fake_codex(self.root, f"pathlib.Path({os.fspath(launched)!r}).write_text('yes')\n")
        process = self.launch(fake, with_flag=True)
        assert process.stdin is not None
        process.stdin.write("An extra constraint.\n")
        process.stdin.flush()
        time.sleep(0.5)
        out, errors = self.finish(process)

        self.assertNotEqual(process.returncode, 0)
        self.assertIn("--context-file", errors)
        self.assertFalse(launched.exists(), "Codex launched and the stdin brief was lost")

    def test_an_open_pipe_that_never_closes_fails_instead_of_hanging(self) -> None:
        read_end, write_end = os.pipe()
        self.addCleanup(os.close, write_end)

        class SilentPipe:
            def isatty(self) -> bool:
                return False

            def fileno(self) -> int:
                return read_end

        try:
            with (
                mock.patch.object(runner, "STDIN_BRIEF_DEADLINE_SECONDS", 0.5),
                mock.patch.object(runner.sys, "stdin", SilentPipe()),
                self.assertRaises(SystemExit) as raised,
            ):
                runner.read_stdin(BRIEF_FLAG, flag_given=False)
        finally:
            os.close(read_end)
        self.assertIn("end of input", str(raised.exception))

    def test_an_idle_pipe_alongside_the_brief_flag_is_not_waited_on(self) -> None:
        fake = write_fake_codex(self.root, "sys.exit(0)\n")
        process = self.launch(fake, with_flag=True, extra=("--dry-run",))
        started = time.monotonic()
        try:
            process.wait(timeout=20)  # stdin stays open and silent throughout
        finally:
            elapsed = time.monotonic() - started
            out, errors = self.finish(process)

        self.assertEqual(process.returncode, 0, errors)
        self.assertLess(elapsed, 5)


class SessionLockTests(LifecycleCase):
    HOLDER = textwrap.dedent(
        """
        import importlib.util, sys
        from pathlib import Path
        spec = importlib.util.spec_from_file_location("holder", sys.argv[1])
        module = importlib.util.module_from_spec(spec)
        sys.modules["holder"] = module
        spec.loader.exec_module(module)
        module.STATE_DIR = Path(sys.argv[2])
        module.acquire_session_lock("gate", Path(sys.argv[3]))
        print("held", flush=True)
        sys.stdin.read()
        """
    )

    def start_holder(self, state: Path) -> subprocess.Popen:
        holder = subprocess.Popen(
            [sys.executable, "-c", self.HOLDER, os.fspath(SCRIPT), os.fspath(state), os.fspath(self.root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        assert holder.stdout is not None
        self.assertEqual(holder.stdout.readline().strip(), "held")
        return holder

    def test_a_live_holder_keeps_the_lock_even_while_its_lock_file_is_empty(self) -> None:
        state = self.root / "state"
        holder = self.start_holder(state)
        try:
            for lock_file in state.glob("*.lock"):
                lock_file.write_text("", encoding="utf-8")
            with mock.patch.object(runner, "STATE_DIR", state):
                with self.assertRaises(SystemExit) as refused:
                    runner.acquire_session_lock("gate", self.root)
            self.assertIn("already has a running pass", str(refused.exception))
        finally:
            holder.kill()
            holder.wait()

    def test_a_dead_holder_releases_the_lock(self) -> None:
        state = self.root / "state"
        holder = self.start_holder(state)
        holder.kill()
        holder.wait()
        with mock.patch.object(runner, "STATE_DIR", state):
            lock = runner.acquire_session_lock("gate", self.root)
            runner.release_session_lock(lock)

    def test_a_refused_launch_leaves_the_running_pass_result_intact(self) -> None:
        release = self.root / "release"
        fake = write_fake_codex(
            self.root,
            f"""
            sys.stdin.read()
            thread_started()
            last_message_path().write_text({SUCCESS!r})
            wait_for({os.fspath(release)!r})
            """,
        )
        first = subprocess.Popen(
            self.cli_command(fake, "shared"),
            cwd=self.root,
            env=self.cli_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert first.stdout is not None
            banner = []
            while not any("Live progress receipt" in line for line in banner):
                line = first.stdout.readline()
                self.assertTrue(line, "first run ended before announcing itself")
                banner.append(line)
            time.sleep(0.5)  # the stand-in has written its last message by now

            second = self.run_cli(fake, "shared")
            release.write_text("go", encoding="utf-8")
            rest, errors = first.communicate(timeout=60)
        finally:
            if first.poll() is None:
                first.kill()

        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already has a running pass", second.stderr)
        self.assertEqual(first.returncode, 0, errors)
        self.assertIn(SUCCESS.splitlines()[0], rest)


if __name__ == "__main__":
    unittest.main()
