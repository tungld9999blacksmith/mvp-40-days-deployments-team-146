#!/usr/bin/env python3
"""
Kiro prompt logger.
Called by Kiro UserPromptSubmit hook — Kiro pipes JSON on stdin.

Stdin payload shape:
  {"userPrompt": "...", "sessionId": "...", ...}

Appends a timestamped entry to .ai-log/session.jsonl.
"""
import json
import os
import select
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))


def git(cmd):
    try:
        return subprocess.check_output(
            cmd, shell=True, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def read_prompt_from_stdin() -> str:
    """
    Đọc JSON từ stdin do Kiro hook gửi vào.
    Dùng select() để không block nếu stdin rỗng.
    """
    try:
        # Kiểm tra stdin có data không (non-blocking, timeout 0.5s)
        if hasattr(select, "select"):
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            if not ready:
                return ""
        raw = sys.stdin.read().strip()
        if not raw:
            return ""
        data = json.loads(raw)
        if isinstance(data, dict):
            # Thử các field phổ biến mà Kiro có thể dùng
            for field in ("userPrompt", "prompt", "message", "text", "content"):
                val = data.get(field)
                if val and isinstance(val, str) and val.strip():
                    return val.strip()[:2000]
    except Exception:
        pass
    return ""


def main():
    # Ưu tiên: stdin JSON → env var USER_PROMPT → fallback
    prompt = (
        read_prompt_from_stdin()
        or os.environ.get("USER_PROMPT", "").strip()
    )

    # Nếu vẫn trống — không ghi log vô nghĩa
    if not prompt:
        sys.exit(0)

    prompt = prompt[:2000]

    origin = git("git remote get-url origin")
    if not origin:
        sys.exit(0)
    repo = origin.rstrip("/").split("/")[-1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    entry = {
        "ts":         datetime.now(VN_TZ).isoformat(),
        "tool":       "kiro",
        "event":      "promptSubmit",
        "session_id": "",
        "model":      "kiro",
        "repo":       repo,
        "branch":     git("git rev-parse --abbrev-ref HEAD"),
        "commit":     git("git rev-parse --short HEAD"),
        "student":    git("git config user.email"),
        "prompt":     prompt,
    }

    log_dir  = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "session.jsonl"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
