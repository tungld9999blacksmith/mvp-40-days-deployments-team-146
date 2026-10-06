"""AI logging checks using fictional input and temporary log files only."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[2]


class LoggingTests(unittest.TestCase):
    def test_windows_launcher_uses_repo_venv_and_preserves_failure(self):
        if os.name != "nt":
            self.skipTest("Windows launcher")
        command = ["cmd", "/d", "/c", "scripts\\_pyrun.cmd"]
        result = subprocess.run(
            command
            + ["-c", "import sys,json,dotenv; print(json.dumps(sys.executable))"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            Path(json.loads(result.stdout)).resolve(),
            (ROOT / ".venv/Scripts/python.exe").resolve(),
        )
        result = subprocess.run(
            command + ["-c", "import sys; sys.exit(7)"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 7)

    def bash(self):
        if os.name == "nt":
            binary = (
                Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
            )
            if binary.exists():
                return str(binary)
        binary = shutil.which("bash")
        if not binary:
            self.skipTest("Bash not installed")
        return binary

    def test_bash_launcher_uses_venv_and_preserves_failure(self):
        command = [self.bash(), "scripts/_pyrun.sh"]
        result = subprocess.run(
            command
            + ["-c", "import sys,json,dotenv; print(json.dumps(sys.executable))"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        expected = ROOT / (
            ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
        )
        self.assertEqual(Path(json.loads(result.stdout)).resolve(), expected.resolve())
        result = subprocess.run(
            command + ["-c", "import sys; sys.exit(7)"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 7)

    def test_codex_hook_records_utf8_in_isolated_directory(self):
        if os.name != "nt":
            self.skipTest("Repo hook command is configured for Windows")
        hook = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
        command = hook["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        prompt = "Kiểm tra AI log: chủ xưởng, tiếng Việt và emoji 🚗"
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "AI_LOG_DIR": directory}
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                input=json.dumps(
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": "fictional-test",
                        "prompt": prompt,
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                capture_output=True,
                check=True,
            )
            self.assertEqual(json.loads(result.stdout)["status"], "logged")
            rows = (
                (Path(directory) / "session.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            self.assertEqual(len(rows), 1)
            entry = json.loads(rows[0])
            self.assertEqual(entry["prompt"], prompt)
            self.assertEqual(entry["tool"], "codex")
            self.assertEqual(entry["session_id"], "fictional-test")

    def submit_module(self, directory):
        spec = importlib.util.spec_from_file_location(
            "submit_log_test", ROOT / "scripts/submit_log.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.SERVER_URL = "http://127.0.0.1/fictional-test"
        module.API_KEY = "fictional-key"
        module.LOG_DIR = Path(directory)
        module.LOG_FILE = Path(directory) / "session.jsonl"
        module.ARCHIVE_DIR = Path(directory) / "archive"
        return module

    def test_submission_failure_keeps_all_local_entries_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            module = self.submit_module(directory)
            content = json.dumps({"prompt": "fictional test", "tool": "codex"}) + "\n"
            module.LOG_FILE.write_text(content, encoding="utf-8")
            with (
                patch.object(
                    module.urllib.request,
                    "urlopen",
                    side_effect=URLError("fictional failure"),
                ),
                self.assertRaises(SystemExit) as result,
            ):
                module.main()
            self.assertEqual(result.exception.code, 1)
            self.assertEqual(module.LOG_FILE.read_text(encoding="utf-8"), content)
            self.assertFalse(module.ARCHIVE_DIR.exists())
            self.assertEqual(list(Path(directory).glob("*.pending.*")), [])

    def test_success_archives_only_after_mock_server_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            module = self.submit_module(directory)
            content = json.dumps({"prompt": "fictional test", "tool": "codex"}) + "\n"
            module.LOG_FILE.write_text(content, encoding="utf-8")
            with patch.object(module.urllib.request, "urlopen") as send:
                send.return_value.__enter__.return_value.status = 200
                module.main()
                self.assertEqual(
                    json.loads(send.call_args.args[0].data)["entries"][0]["prompt"],
                    "fictional test",
                )
            self.assertFalse(module.LOG_FILE.exists())
            archives = list(module.ARCHIVE_DIR.glob("*.jsonl"))
            self.assertEqual(len(archives), 1)
            self.assertEqual(archives[0].read_text(encoding="utf-8"), content)

    def test_missing_server_reports_failure_without_touching_log(self):
        with tempfile.TemporaryDirectory() as directory:
            module = self.submit_module(directory)
            module.SERVER_URL = ""
            module.LOG_FILE.write_text("fictional entry\n", encoding="utf-8")
            with patch.object(module.urllib.request, "urlopen") as send:
                with self.assertRaises(SystemExit) as result:
                    module.main()
                send.assert_not_called()
            self.assertEqual(result.exception.code, 1)
            self.assertEqual(
                module.LOG_FILE.read_text(encoding="utf-8"), "fictional entry\n"
            )

    def test_pre_push_reports_both_failures_and_does_not_block_push(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "scripts"
            folder.mkdir()
            shutil.copyfile(
                ROOT / "scripts/pre_push_ai_log.sh", folder / "pre_push_ai_log.sh"
            )
            (folder / "_pyrun.sh").write_text(
                "#!/usr/bin/env bash\nexit 7\n", encoding="utf-8"
            )
            result = subprocess.run(
                [self.bash(), "scripts/pre_push_ai_log.sh"],
                cwd=directory,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"prompt sweep failed", result.stderr)
            self.assertIn(b"log submission failed", result.stderr)

    def test_missing_dotenv_reports_configuration_error_without_sending(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".env").write_text(
                "AI_LOG_SERVER=http://127.0.0.1/fictional-test\n", encoding="utf-8"
            )
            # -S disables site-packages, deliberately simulating missing dotenv.
            result = subprocess.run(
                [sys.executable, "-S", str(ROOT / "scripts/submit_log.py")],
                cwd=directory,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"Cannot read .env", result.stderr)
            self.assertFalse(Path(directory, ".ai-log").exists())


if __name__ == "__main__":
    unittest.main()
