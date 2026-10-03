import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clax


USAGE_TEXT = """You are currently using your subscription to power your Claude Code usage

Current session: 30% used · resets Oct 3, 12:30pm (America/Sao_Paulo)
Current week (all models): 70% used · resets Oct 9, 12am (America/Sao_Paulo)
Current week (Fable): 0% used · resets Oct 9, 12am (America/Sao_Paulo)
"""


def stream(*events):
    return "".join(json.dumps(event) + "\n" for event in events)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class FakeProcess:
    def __init__(self, output: str, status: int = 0):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(output)
        self.status = status
        self.written = ""
        original_close = self.stdin.close

        def close():
            self.written = self.stdin.getvalue()
            original_close()

        self.stdin.close = close

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return self.status


class ProfileCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.profiles = base / "profiles"
        self.shared = base / "shared"
        self.home = base / "home"
        self.home.mkdir()
        patcher = mock.patch.dict(os.environ, {"CLAX_PROFILES_HOME": str(self.profiles),
                                               "CLAX_SHARED_STATE_HOME": str(self.shared)})
        patcher.start()
        self.addCleanup(patcher.stop)
        home_patcher = mock.patch.object(clax.Path, "home", return_value=self.home)
        home_patcher.start()
        self.addCleanup(home_patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def write_profile(self, number, token="token", expires_in=3600, email="ana@example.com"):
        profile = self.profiles / str(number)
        profile.mkdir(parents=True, exist_ok=True)
        (profile / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
            "accessToken": token, "expiresAt": int((time.time() + expires_in) * 1000)}}))
        (profile / ".claude.json").write_text(json.dumps({"oauthAccount": {"emailAddress": email}}))
        return profile


class UsageTests(ProfileCase):
    def test_usage_api_response_parsing(self):
        profile = self.write_profile(1)
        body = json.dumps({
            "five_hour": {"utilization": 30.0, "resets_at": "2026-10-03T15:30:00.342045+00:00"},
            "seven_day": {"utilization": 70.0, "resets_at": "2026-10-09T03:00:00+00:00"},
        }).encode()
        with mock.patch.object(clax.urllib.request, "urlopen", return_value=FakeResponse(body)) as urlopen:
            result = clax.usage_limits("claude", profile)
        self.assertEqual(result.email, "ana")
        self.assertEqual((result.five, result.week), (70, 30))
        self.assertEqual(result.week_reset, 1791514800)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer token")

    def test_expired_token_uses_claude_usage_command(self):
        profile = self.write_profile(1, expires_in=-60)
        with mock.patch.object(clax, "usage_via_cli", return_value=USAGE_TEXT) as cli, \
                mock.patch.object(clax, "usage_api") as api:
            result = clax.usage_limits("claude", profile)
        cli.assert_called_once()
        api.assert_not_called()
        self.assertEqual((result.email, result.five, result.week), ("ana", 70, 30))
        self.assertIsNotNone(result.five_reset)

    def test_usage_text_without_subscription_is_unavailable(self):
        self.assertIsNone(clax.usage_from_text("Total cost: $0.0000\n", "ana"))

    def test_bar_data_skips_unavailable_accounts(self):
        rows = [(1, True, clax.Usage("ana", 70, 2000000000, 30, 2000001000)),
                (2, True, None), (3, False, None)]
        output = io.StringIO()
        with mock.patch.object(clax, "collect_profiles", return_value=rows), \
                mock.patch("sys.stdout", output):
            clax.bar_data("claude")
        lines = output.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("1\tana\t70\t"))
        self.assertTrue(lines[0].endswith("\t30"))


class LimitDetectionTests(unittest.TestCase):
    def test_limit_result_is_detected(self):
        event = {"type": "result", "subtype": "success", "is_error": True,
                 "result": "You've hit your session limit · resets 3pm"}
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(clax.render_event(event), "limit")

    def test_limit_in_errors_list_is_detected(self):
        event = {"type": "result", "subtype": "error_during_execution", "is_error": True,
                 "errors": ["Claude AI usage limit reached|1759500000"]}
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(clax.render_event(event), "limit")

    def test_rejected_rate_limit_event(self):
        rejected = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "isUsingOverage": False}}
        allowed = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning"}}
        self.assertEqual(clax.render_event(rejected), "rejected")
        self.assertIsNone(clax.render_event(allowed))

    def test_transient_rate_limit_and_warnings_are_ignored(self):
        transient = {"type": "result", "subtype": "success", "is_error": True,
                     "result": "API Error: Request rejected (429) · this may be a temporary capacity issue."}
        warning = {"type": "assistant", "error": "rate_limit",
                   "message": {"content": [{"type": "text", "text": "You've used 90% of your session limit"}]}}
        normal = {"type": "result", "subtype": "success", "is_error": False,
                  "result": "You've hit your goal: all tests pass."}
        with mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(clax.render_event(transient), "error")
            self.assertIsNone(clax.render_event(warning))
            self.assertIsNone(clax.render_event(normal))


class AutoModeTests(ProfileCase):
    def test_auto_resumes_with_next_eligible_account(self):
        rows = [(1, True, clax.Usage("ana", 80, 2000000000, 80, 2000001000)),
                (2, True, clax.Usage("bia", 60, 2000000000, 60, 2000001000))]
        first = FakeProcess(stream(
            {"type": "system", "subtype": "init", "session_id": "x", "model": "m"},
            {"type": "assistant", "error": "rate_limit",
             "message": {"content": [{"type": "text", "text": "You've hit your session limit · resets 3pm"}]}},
            {"type": "result", "subtype": "success", "is_error": True,
             "result": "You've hit your session limit · resets 3pm"}), 1)
        second = FakeProcess(stream(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "concluido"}]}},
            {"type": "result", "subtype": "success", "is_error": False, "result": "concluido"}))
        with mock.patch.object(clax, "collect_profiles", return_value=rows), \
                mock.patch.object(clax.subprocess, "Popen", side_effect=[first, second]) as popen, \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            result = clax.auto_mode("claude", ["fazer tarefa"])
        self.assertEqual(result, 0)
        self.assertEqual(popen.call_count, 2)
        first_args = popen.call_args_list[0].args[0]
        second_args = popen.call_args_list[1].args[0]
        session_id = first_args[first_args.index("--session-id") + 1]
        self.assertTrue(clax.UUID.fullmatch(session_id))
        self.assertEqual(second_args[second_args.index("--resume") + 1], session_id)
        self.assertEqual(popen.call_args_list[0].kwargs["env"]["CLAUDE_CONFIG_DIR"], str(self.profiles / "1"))
        self.assertEqual(popen.call_args_list[1].kwargs["env"]["CLAUDE_CONFIG_DIR"], str(self.profiles / "2"))
        self.assertEqual(first.written, "fazer tarefa")
        self.assertEqual(second.written, clax.CONTINUATION)
        self.assertIn("--permission-mode", first_args)

    def test_auto_switches_on_rejection_followed_by_error(self):
        rows = [(1, True, clax.Usage("ana", 80, 2000000000, 80, 2000001000)),
                (2, True, clax.Usage("bia", 60, 2000000000, 60, 2000001000))]
        rejected = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}
        first = FakeProcess(stream(rejected, {"type": "result", "subtype": "success", "is_error": True,
                                              "result": "API Error: 429"}), 1)
        finished = FakeProcess(stream(rejected, {"type": "result", "subtype": "success", "is_error": False,
                                                 "result": "concluido em outro modelo"}))
        with mock.patch.object(clax, "collect_profiles", return_value=rows), \
                mock.patch.object(clax.subprocess, "Popen", side_effect=[first, finished]) as popen, \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            result = clax.auto_mode("claude", ["fazer tarefa"])
        self.assertEqual(result, 0)
        self.assertEqual(popen.call_count, 2)

    def test_auto_stops_on_regular_error(self):
        rows = [(1, True, clax.Usage("ana", 80, 2000000000, 80, 2000001000)),
                (2, True, clax.Usage("bia", 60, 2000000000, 60, 2000001000))]
        failed = FakeProcess(stream({"type": "result", "subtype": "success", "is_error": True,
                                     "result": "API Error: 500"}), 1)
        with mock.patch.object(clax, "collect_profiles", return_value=rows), \
                mock.patch.object(clax.subprocess, "Popen", side_effect=[failed]) as popen, \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            result = clax.auto_mode("claude", ["fazer tarefa"])
        self.assertEqual(result, 1)
        self.assertEqual(popen.call_count, 1)


@unittest.skipIf(os.name == "nt", "symlinks de arquivo exigem modo de desenvolvedor no Windows")
class ProfileSetupTests(ProfileCase):
    def test_prepare_profile_links_shared_state(self):
        (self.shared / "skills").mkdir(parents=True)
        (self.shared / "settings.json").write_text("{}")
        profile = clax.prepare_profile(3)
        self.assertEqual((profile / "projects").resolve(), (self.shared / "projects").resolve())
        self.assertTrue((profile / "skills").is_symlink())
        self.assertTrue((profile / "settings.json").is_symlink())
        self.assertFalse((profile / "agents").exists())
        self.assertEqual(profile.stat().st_mode & 0o777, 0o700)

    def test_prepare_profile_keeps_existing_entries(self):
        profile = self.profiles / "4"
        (profile / "projects").mkdir(parents=True)
        (profile / "projects" / "old.jsonl").write_text("{}")
        clax.prepare_profile(4)
        self.assertFalse((profile / "projects").is_symlink())
        self.assertTrue((profile / "projects" / "old.jsonl").exists())

    def test_seed_copies_only_whitelisted_preferences(self):
        (self.home / ".claude.json").write_text(json.dumps({
            "hasCompletedOnboarding": True, "theme": "dark", "mcpServers": {"x": {}},
            "oauthAccount": {"emailAddress": "dono@example.com"}, "userID": "abc"}))
        profile = clax.prepare_profile(5)
        seeded = json.loads((profile / ".claude.json").read_text())
        self.assertEqual(seeded, {"hasCompletedOnboarding": True, "theme": "dark", "mcpServers": {"x": {}}})
        self.assertEqual((profile / ".claude.json").stat().st_mode & 0o777, 0o600)

    def test_session_inside_profile_does_not_redirect_shared_state(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.profiles / "2")}):
            os.environ.pop("CLAX_SHARED_STATE_HOME")
            self.assertEqual(clax.roots()[1], self.home / ".claude")
            self.assertNotIn("CLAUDE_CONFIG_DIR", clax.base_env())


if __name__ == "__main__":
    unittest.main()
