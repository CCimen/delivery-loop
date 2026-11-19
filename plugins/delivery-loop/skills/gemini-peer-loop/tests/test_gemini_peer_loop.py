from __future__ import annotations

import importlib.util
import io
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "gemini_peer_loop.py"
SPEC = importlib.util.spec_from_file_location("gemini_peer_loop", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
gpl = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gpl
SPEC.loader.exec_module(gpl)

CONVERSATION = "055a398f-db14-4c5f-abbb-1bf03f8120a7"
OTHER_CONVERSATION = "7d1f7c3e-0b55-4a8e-9a43-3c0f6c1f2b10"
GREEN = "VERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 9\n\n## Findings\nnone"
BLOCKED = "VERDICT: blocked\nGREEN_LIGHT: no\nMIN_SCORE: 3\n\n## Findings\nF1"


def parse(*flags: str, environ: dict[str, str] | None = None):
    return gpl.parse_args(["--question", "Review this change.", *flags], environ=environ or {})


class SettingsTests(unittest.TestCase):
    def test_defaults_to_neon_and_reads_only_its_own_variables(self) -> None:
        args = parse(environ={"CODEX_PEER_LOOP_MODEL": "gpt-6.2-sol"})
        self.assertEqual((args.model, args.effort), ("gemini-4-neon", "medium"))
        args = parse(environ={"GEMINI_PEER_LOOP_MODEL": "gemini-4-hydrogen"})
        self.assertEqual(args.model, "gemini-4-hydrogen")

    def test_auto_effort_stops_at_the_models_top_rung(self) -> None:
        complex_gate = ("--phase", "commit-gate", "--complexity", "complex")
        self.assertEqual(parse(*complex_gate).effort, "xhigh")
        self.assertEqual(parse(*complex_gate, "--model", "gemini-4-argon").effort, "high")
        # An explicit pin passes through; agy refuses it loudly.
        pinned = parse(*complex_gate, "--model", "gemini-4-argon", "--effort", "xhigh")
        self.assertEqual(pinned.effort, "xhigh")

    def test_efforts_agy_lacks_are_refused(self) -> None:
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            parse("--effort", "ultra")

    def test_a_resumed_session_keeps_its_saved_settings(self) -> None:
        args = parse()
        gpl.apply_session_settings(args, {"model": "gemini-4-argon", "complexity": "critical"})
        self.assertEqual((args.model, args.complexity), ("gemini-4-argon", "critical"))

    def test_other_platforms_are_refused(self) -> None:
        with mock.patch.object(gpl.sys, "platform", "linux"):
            with self.assertRaises(SystemExit) as raised:
                gpl.refuse_unsupported_platform()
        self.assertIn("macOS", str(raised.exception))
        with mock.patch.object(gpl.sys, "platform", "darwin"):
            gpl.refuse_unsupported_platform()


class ReadOnlyLaunchTests(unittest.TestCase):
    def test_command_keeps_the_review_read_only(self) -> None:
        args = parse()
        args.agy_bin = "/path/to/agy"
        for thread_id in (None, CONVERSATION):
            with self.subTest(resume=thread_id is not None):
                command = gpl.gemini_command(args, [Path("/repo")], thread_id)
                self.assertNotIn("--add-dir", command)
                for flag in ("--sandbox", "--disable-slash-commands", "--json-schema"):
                    self.assertIn(flag, command)
                self.assertEqual(command[command.index("--agent") + 1], gpl.GEMINI_AGENT)
                settings = json.loads(command[command.index("--settings") + 1])
                for rule in ("write_file(*)", "unsandboxed(*)", "mcp(*)", "read_url(*)", "execute_url(*)"):
                    self.assertIn(rule, settings["permissions"]["deny"])
                self.assertEqual(settings["permissions"]["allow"], ["read_file(/repo)"])
                self.assertEqual(settings["toolPermission"], "proceed-in-sandbox")
                self.assertEqual(thread_id in command, thread_id is not None)
        agent = gpl.gemini_agent_definition()
        self.assertIn("mainAgent: true", agent)
        self.assertIn("commandExecutionPolicy: sandbox", agent)
        self.assertNotIn("schedule", agent)

    def test_only_the_workspace_stays_writable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp).resolve() / "state"
            with mock.patch.object(gpl, "STATE_DIR", state):
                workspace = gpl.create_workspace()
                paths = gpl.read_only_paths([Path("/repo")], Path(tmp) / "artifacts", workspace)
                environment = gpl.gemini_environment(workspace)
                agent_file = workspace / ".agents" / "agents" / f"{gpl.GEMINI_AGENT}.md"
                self.assertTrue(agent_file.is_file())
                self.assertEqual(workspace.parent, state / "workspaces")
        for path in (Path("/repo"), state, workspace / ".agents", Path("/tmp"), Path("/private/tmp")):
            self.assertIn(path, paths)
        cache = Path.home() / ".cache"
        if cache.is_dir():
            self.assertIn(cache, paths)
        self.assertIn(Path(tempfile.gettempdir()).resolve(), paths)
        self.assertNotIn(workspace, paths)
        self.assertEqual(environment["TMPDIR"], f"{workspace / 'tmp'}/")

    def test_workspaces_inside_a_reviewed_dir_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            with mock.patch.object(gpl, "STATE_DIR", repo / ".state"):
                with self.assertRaises(SystemExit) as raised:
                    gpl.check_workspace_location([repo])
                gpl.check_workspace_location([repo / "elsewhere"])
        self.assertIn("GEMINI_PEER_LOOP_STATE_DIR", str(raised.exception))

    def test_prompt_names_gemini_and_the_absolute_root(self) -> None:
        root = Path.cwd()
        prompt = gpl.build_prompt(parse(), "", root)
        self.assertTrue(prompt.startswith("You are Gemini, a read-only skeptical staff reviewer"))
        self.assertIn(f"`git -C {root}`", prompt)

    def test_resume_skeleton_keeps_agy_and_the_model(self) -> None:
        args = parse("--phase", "plan", "--model", "gemini-4-argon")
        args.agy_bin = "/path/to/agy"
        resumed = gpl.parse_args(shlex.split(gpl.next_command(args))[1:], environ={})
        self.assertEqual((resumed.agy_bin, resumed.model), ("/path/to/agy", "gemini-4-argon"))
        self.assertEqual(resumed.phase, "verification")


def event(kind: str, payload: dict, **top: object) -> str:
    return json.dumps({"event": kind, kind: payload, **top})


def init(agent: str = gpl.GEMINI_AGENT, mode: str = "proceed-in-sandbox", conversation: str = CONVERSATION) -> str:
    return event("init", {"agent": agent, "permission_mode": mode}, conversation_id=conversation)


def step(step_type: str, tool: str = "", text: str = "", state: str = "DONE", conversation: object = CONVERSATION) -> str:
    payload = {"step_index": 0, "state": state, "step_type": step_type, "text_delta": text}
    if conversation is not None:
        payload["conversation_id"] = conversation
    if tool:
        payload["tool_name"] = tool
    return event("step_update", payload)


def fields(review: str) -> dict[str, object]:
    """A review text as agy's structured output: the header as typed fields,
    the rest as the body. Text without a header gets the invalid verdict a
    real run produced (REVISE)."""
    lines = review.split("\n")
    head = dict(line.split(": ", 1) for line in lines[:3] if ": " in line)
    if not head:
        return {"verdict": "REVISE", "green_light": "no", "min_score": 4, "review": review}
    return {
        "verdict": head["VERDICT"],
        "green_light": head["GREEN_LIGHT"],
        "min_score": int(head["MIN_SCORE"]),
        "review": "\n".join(lines[3:]).strip(),
    }


def result(review: str | None, conversation: object = CONVERSATION) -> str:
    payload: dict[str, object] = {"status": "SUCCESS", "response": "Reading the diff. " + (review or "")}
    if conversation is not None:
        payload["conversation_id"] = conversation
    if review is not None:
        payload["structured_output"] = fields(review)
    return event("result", payload)


class StreamContractTests(unittest.TestCase):
    def tracker(self, *lines: str, **options):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = gpl.ProgressTracker(Path(tmp) / "run.progress", **options)
            for line in lines:
                tracker.handle_line(line)
        return tracker

    def test_the_review_is_the_structured_result_not_any_text_step(self) -> None:
        steps = (
            step("agent_response", text="Waiting for command 5 to finish.\n"),
            step("tool", "run_command"),
            step("agent_response", text=GREEN),
            step("agent_response", text="Correction: F1 blocks; this is not green."),
        )
        reviewed = self.tracker(init(), *steps, result(BLOCKED))
        unreviewed = self.tracker(init(), *steps, result(None))
        self.assertEqual(reviewed.review, BLOCKED)
        self.assertEqual(reviewed.thread_id, CONVERSATION)
        self.assertIsNone(reviewed.unusable())
        self.assertEqual(unreviewed.review, "")
        self.assertIn("without a review", unreviewed.unusable())

    def test_every_documented_step_type_is_part_of_a_valid_stream(self) -> None:
        # agy's headless docs list user_input, agent_response, tool and
        # checkpoint; system_message and finish appear in real runs.
        steps = [
            step(kind, "run_command" if kind == "tool" else "")
            for kind in ("user_input", "system_message", "agent_response", "tool", "checkpoint", "finish")
        ]
        tracker = self.tracker(init(), *steps, result(GREEN))
        self.assertIsNone(tracker.violation)
        self.assertIsNone(tracker.unusable())

    def test_the_header_comes_from_the_typed_fields(self) -> None:
        # The body repeats a header that contradicts the fields: the fields win.
        body = {"verdict": "blocked", "green_light": "no", "min_score": 3,
                "review": "VERDICT: green\nGREEN_LIGHT: yes\nMIN_SCORE: 9\n\n## Findings\nF1"}
        payload = {"status": "SUCCESS", "conversation_id": CONVERSATION, "structured_output": body}
        tracker = self.tracker(init(), event("result", payload))
        self.assertEqual(tracker.review, BLOCKED)
        self.assertIsNone(tracker.unusable())
        revise = self.tracker(init(), result("Looks fine to me."))
        self.assertIn("no valid header", revise.unusable())

    def test_contract_breaks_abort_the_moment_they_appear(self) -> None:
        cases = {
            "schedule": (init(), step("tool", "schedule", state="RUNNING")),
            "agent": (init(agent="default"),),
            "permission mode": (init(mode="request-review"),),
            "mixes conversations": (init(), step("tool", "run_command", conversation=OTHER_CONVERSATION)),
            "second result": (init(), result(GREEN), result(GREEN)),
            "second init": (init(), init()),
        }
        for expected, lines in cases.items():
            with self.subTest(expected):
                tracker = self.tracker(*lines)
                self.assertTrue(tracker.abort.is_set())
                self.assertIn(expected, tracker.violation)
                self.assertIn(expected, tracker.unusable())

    def test_incomplete_or_unbound_results_are_unusable(self) -> None:
        cases = {
            "without a result": (init(),),
            "names no conversation": (init(), result(GREEN, conversation=None)),
            "mixes conversations": (init(), result(GREEN, conversation=OTHER_CONVERSATION)),
            "no valid header": (init(), result("Looks fine to me.")),
        }
        for expected, lines in cases.items():
            with self.subTest(expected):
                self.assertIn(expected, self.tracker(*lines).unusable())

    def test_the_conversation_id_comes_from_init_only(self) -> None:
        tracker = self.tracker(step("tool", "run_command"), result(GREEN))
        self.assertEqual(tracker.thread_id, "")

    def test_every_line_follows_one_grammar(self) -> None:
        cases = {
            "numeric result id": ((init(), result(GREEN, conversation=123)), "mixes conversations"),
            "numeric init id": ((init(conversation=7),), "no canonical conversation id"),
            "result before init": ((result(GREEN),), "before init"),
            "step before init": ((step("agent_response", text="hi"),), "before init"),
            "step without id": ((init(), step("agent_response", conversation=None)), "names no conversation"),
            "tool without name": ((init(), step("tool", state="ACTIVE")), "tool step without a name"),
            "unknown event": ((init(), event("telemetry", {"conversation_id": CONVERSATION})), "unknown event 'telemetry'"),
            "unknown step type": ((init(), step("plan")), "unknown step type 'plan'"),
            "event after result": ((init(), result(GREEN), step("agent_response", text="late")), "after its result"),
            "not json": ((init(), "warning: update available"), "not a JSON event"),
        }
        for name, (lines, expected) in cases.items():
            with self.subTest(name):
                tracker = self.tracker(*lines)
                self.assertTrue(tracker.abort.is_set())
                self.assertIn(expected, tracker.violation)
                self.assertIn(expected, tracker.unusable())

    def test_the_id_is_published_only_from_an_accepted_init(self) -> None:
        resumed = self.tracker(init(conversation=OTHER_CONVERSATION), expected_thread_id=CONVERSATION)
        self.assertTrue(resumed.abort.is_set())
        self.assertIn("stored", resumed.violation)
        self.assertEqual(resumed.thread_id, "")
        stored: list[str] = []
        rejected = self.tracker(init(agent="default"), on_thread_id=stored.append)
        self.assertEqual((stored, rejected.thread_id), ([], ""))
        accepted = self.tracker(init(), on_thread_id=stored.append)
        self.assertEqual((stored, accepted.thread_id), ([CONVERSATION], CONVERSATION))

    def test_a_tracker_failure_aborts_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tracker = gpl.ProgressTracker(Path(tmp) / "run.progress")
            with mock.patch.object(tracker, "_write_locked", side_effect=OSError("disk full")):
                tracker.handle_line(init())
        self.assertTrue(tracker.abort.is_set())
        self.assertIn("disk full", tracker.violation)

    def test_a_failed_sidecar_still_feeds_every_line_to_the_contract_check(self) -> None:
        class FullDisk(io.StringIO):
            def write(self, text: str) -> int:
                raise OSError(28, "No space left on device")

        lines = (init(), step("tool", "schedule", state="ACTIVE"))
        stream = io.BytesIO(("\n".join(lines) + "\n").encode())
        failures: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            tracker = gpl.ProgressTracker(Path(tmp) / "run.progress")
            sink = Path(tmp) / "run.stdout.txt"
            real_open = Path.open

            def sink_open(path: Path, *args, **kwargs):
                return FullDisk() if path == sink else real_open(path, *args, **kwargs)

            with mock.patch.object(Path, "open", autospec=True, side_effect=sink_open):
                gpl.drain_stream(stream, sink, gpl.TailBuffer(10_000), failures, tracker.handle_line)
        self.assertTrue(failures)
        self.assertTrue(tracker.abort.is_set())
        self.assertIn("schedule", tracker.violation)


FAKE_AGY = """#!__PYTHON__
import json, os, sys, time
argv = sys.argv[1:]
if argv == ["--version"]:
    print("9.9.9-fake")
    sys.exit(0)
scenario = os.environ.get("FAKE_AGY_SCENARIO", "green")
stdin = sys.stdin.read()
agent = argv[argv.index("--agent") + 1]
with open(os.environ["FAKE_AGY_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "cwd": os.getcwd(), "argv": argv, "stdin": stdin, "tmpdir": os.environ.get("TMPDIR"),
        "agent_file": os.path.isfile(os.path.join(".agents", "agents", agent + ".md")),
    }) + "\\n")
conversation = "__CONVERSATION__"
if "--conversation" in argv:
    conversation = argv[argv.index("--conversation") + 1]
if scenario == "otherresume":
    conversation = "__OTHER__"
def emit(kind, payload, top=None):
    event = {"event": kind, kind: payload}
    event.update(top or {})
    print(json.dumps(event), flush=True)
if scenario == "sleep":
    time.sleep(60)
emit("init", {"agent": "default" if scenario == "wrongagent" else agent,
              "permission_mode": "proceed-in-sandbox"}, {"conversation_id": conversation})
if scenario in ("wrongagent", "otherresume"):
    time.sleep(60)
tool = "schedule" if scenario == "disallowed" else "run_command"
emit("step_update", {"conversation_id": conversation, "step_index": 0, "state": "RUNNING",
                     "step_type": "tool", "tool_name": tool})
if scenario == "disallowed":
    time.sleep(60)
if os.environ.get("FAKE_AGY_TOUCH"):
    with open(os.environ["FAKE_AGY_TOUCH"], "w", encoding="utf-8") as handle:
        handle.write("changed during the pass")
review = {"blocked": __BLOCKED__, "badheader": __BADHEADER__}.get(scenario, __GREEN__)
result = {"conversation_id": conversation, "status": "SUCCESS", "response": "Reading. " + review["review"]}
if scenario == "mixed":
    result["conversation_id"] = "__OTHER__"
if scenario == "noid":
    del result["conversation_id"]
if scenario != "empty":
    result["structured_output"] = review
emit("result", result)
if scenario == "tworesults":
    emit("result", result)
"""


@unittest.skipUnless(sys.platform == "darwin", "the runner refuses other platforms")
class RunnerBoundaryTests(unittest.TestCase):
    """The whole runner against an agy stand-in that streams stream-json."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.root = self.base / "repo"
        (self.root / "sub").mkdir(parents=True)
        self.state = self.base / "state"
        self.fake = self.base / "agy"
        self.fake.write_text(
            FAKE_AGY.replace("__PYTHON__", sys.executable)
            .replace("__CONVERSATION__", CONVERSATION)
            .replace("__OTHER__", OTHER_CONVERSATION)
            .replace("__BLOCKED__", repr(fields(BLOCKED)))
            .replace("__BADHEADER__", repr(fields("Looks fine to me.")))
            .replace("__GREEN__", repr(fields(GREEN))),
            encoding="utf-8",
        )
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IXUSR)
        self.seen: set[Path] = set()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_pass(self, scenario: str, *flags: str, **environment: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable, os.fspath(SCRIPT),
                "--session", "gemini-e2e",
                "--question", "Review the Gemini contract.",
                "--agy-bin", os.fspath(self.fake),
                "--no-print-next-command",
                "--require-green",
                *flags,
            ],
            cwd=self.root,
            env={
                **os.environ,
                "GEMINI_PEER_LOOP_STATE_DIR": os.fspath(self.state),
                "FAKE_AGY_LOG": os.fspath(self.base / "agy.log"),
                "FAKE_AGY_SCENARIO": scenario,
                **environment,
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

    def status(self) -> str:
        """The one receipt this test has not read yet."""
        receipts = set((self.root / ".gemini-peer-loop" / "artifacts").glob("*.status")) - self.seen
        self.assertEqual(len(receipts), 1)
        receipt = receipts.pop()
        self.seen.add(receipt)
        return receipt.read_text(encoding="utf-8")

    def calls(self) -> list[dict]:
        return [json.loads(line) for line in (self.base / "agy.log").read_text().splitlines()]

    def test_new_and_resumed_passes_stay_in_one_conversation_from_fresh_workspaces(self) -> None:
        first = self.run_pass("green", "--new-session", "--path", "sub")
        self.assertEqual(first.returncode, 0, first.stderr)
        first_status = self.status()
        second = self.run_pass("green", "--phase", "verification")
        self.assertEqual(second.returncode, 0, second.stderr)
        second_status = self.status()
        calls = self.calls()

        for receipt in (first_status, second_status):
            for line in ("reviewer=gemini", "thread_identity_status=passed", "green_verdict=true",
                         "process_group=clean", "pass_history=recorded", f"thread_id={CONVERSATION}",
                         "agy_version=9.9.9-fake"):
                self.assertIn(line, receipt)
        self.assertIn("command_kind=resume", second_status)
        self.assertNotIn("--conversation", calls[0]["argv"])
        self.assertEqual(calls[1]["argv"][calls[1]["argv"].index("--conversation") + 1], CONVERSATION)
        self.assertNotEqual(calls[0]["cwd"], calls[1]["cwd"])
        for call in calls:
            workspace = Path(call["cwd"])
            self.assertEqual(workspace.parent, self.state / "workspaces")
            self.assertFalse(workspace.exists(), "the workspace outlived its pass")
            self.assertEqual(call["tmpdir"], f"{workspace / 'tmp'}/")
            self.assertTrue(call["agent_file"])
            lines = call["stdin"].splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn(os.fspath(self.root), json.loads(lines[0])["message"]["content"])
        # Relative paths would point into agy's workspace; they arrive absolute.
        self.assertIn(f"- {self.root / 'sub'}", json.loads(calls[0]["stdin"])["message"]["content"])

    def test_runs_without_a_usable_review_exit_3_and_are_not_counted(self) -> None:
        for scenario in ("empty", "mixed", "noid", "tworesults", "badheader"):
            with self.subTest(scenario):
                completed = self.run_pass(scenario, "--new-session")
                receipt = self.status()
                self.assertEqual(completed.returncode, 3, completed.stderr)
                self.assertIn("pass_history=not counted", receipt)
                self.assertIn("thread_identity_status=unverified", receipt)
                self.assertIn("green_verdict=false", receipt)
                self.assertIn("no usable review", completed.stderr)
                if scenario == "badheader":
                    # The unusable text is kept, labelled, for the reader.
                    self.assertIn("for reference only", completed.stdout)
                    self.assertIn("Looks fine to me.", completed.stdout)

    def test_contract_breaks_stop_agy_at_once(self) -> None:
        for scenario, reason in (("disallowed", "schedule"), ("wrongagent", "'default'")):
            with self.subTest(scenario):
                started = time.monotonic()
                completed = self.run_pass(scenario, "--new-session")
                elapsed = time.monotonic() - started
                receipt = self.status()
                self.assertEqual(completed.returncode, 3, completed.stderr)
                self.assertLess(elapsed, 20)
                self.assertIn(reason, completed.stderr)
                self.assertIn("process_group=terminated", receipt)
                self.assertIn("pass_history=not counted", receipt)

    def test_a_timeout_stops_the_group(self) -> None:
        completed = self.run_pass("sleep", "--new-session", "--timeout-seconds", "1")
        receipt = self.status()
        self.assertEqual(completed.returncode, 124, completed.stderr)
        self.assertIn("timed_out=true", receipt)
        self.assertIn("process_group=terminated", receipt)

    def test_a_concurrent_pass_is_refused(self) -> None:
        with mock.patch.object(gpl, "STATE_DIR", self.state):
            lock = gpl.acquire_session_lock("gemini-e2e", self.root)
            try:
                completed = self.run_pass("green", "--new-session")
            finally:
                gpl.release_session_lock(lock)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("already has a running pass", completed.stderr)
        self.assertFalse((self.base / "agy.log").exists())

    def test_the_gate_budget_is_spent_after_three_passes(self) -> None:
        outputs = [
            self.run_pass("blocked", "--new-session", "--phase", "commit-gate"),
            self.run_pass("blocked", "--phase", "verification"),
            self.run_pass("blocked", "--phase", "verification"),
        ]
        self.assertEqual([completed.returncode for completed in outputs], [2, 2, 2])
        self.assertNotIn("Pass budget spent", outputs[1].stdout)
        self.assertIn("Pass budget spent", outputs[2].stdout)

    def test_drift_during_the_pass_fails_the_gate(self) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "base"],
            cwd=self.root,
            check=True,
        )
        completed = self.run_pass("green", "--new-session", FAKE_AGY_TOUCH=os.fspath(self.root / "sub" / "new.txt"))
        receipt = self.status()
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("content_drift=true", receipt)
        self.assertIn("green_verdict=true", receipt)

    def test_a_replacement_that_cannot_launch_keeps_the_old_session(self) -> None:
        first = self.run_pass("green", "--new-session")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.status()
        refused = self.run_pass("green", "--new-session", "--agy-bin", os.fspath(self.base / "missing"))
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("agy executable not found", refused.stderr)
        resumed = self.run_pass("green", "--phase", "verification")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        receipt = self.status()
        self.assertIn("command_kind=resume", receipt)
        self.assertIn(f"thread_id={CONVERSATION}", receipt)

    def test_a_replacement_whose_workspace_fails_keeps_the_old_session(self) -> None:
        first = self.run_pass("green", "--new-session")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.status()
        workspaces = self.state / "workspaces"
        workspaces.rmdir()
        workspaces.write_text("not a directory", encoding="utf-8")
        refused = self.run_pass("green", "--new-session")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("workspace", refused.stderr)
        workspaces.unlink()
        resumed = self.run_pass("green", "--phase", "verification")
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        receipt = self.status()
        self.assertIn("command_kind=resume", receipt)
        self.assertIn(f"thread_id={CONVERSATION}", receipt)

    def test_a_resume_into_another_conversation_stops_at_init(self) -> None:
        first = self.run_pass("green", "--new-session")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.status()
        started = time.monotonic()
        resumed = self.run_pass("otherresume", "--phase", "verification")
        elapsed = time.monotonic() - started
        receipt = self.status()
        self.assertEqual(resumed.returncode, 3, resumed.stderr)
        self.assertLess(elapsed, 20)
        self.assertIn("stored", resumed.stderr)
        self.assertIn("process_group=terminated", receipt)
        self.assertIn("pass_history=not counted", receipt)

    def test_a_manifest_error_counts_the_pass_but_never_passes_the_gate(self) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        fake_git = bin_dir / "git"
        fake_git.write_text(
            "#!/bin/sh\n"
            'case " $* " in *" ls-files "*) echo "fatal: index unreadable" >&2; exit 128;; esac\n'
            f'exec {shlex.quote(subprocess.check_output(["which", "git"], text=True).strip())} "$@"\n',
            encoding="utf-8",
        )
        fake_git.chmod(0o755)
        completed = self.run_pass("green", "--new-session", PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        receipt = self.status()
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertRegex(receipt, r"manifest_error=\S")
        self.assertIn("pass_history=recorded", receipt)
        self.assertIn("green_verdict=true", receipt)


if __name__ == "__main__":
    unittest.main()
