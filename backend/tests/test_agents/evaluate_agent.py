"""Evaluate the current Agent; old benchmark results are never overwritten."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from tests.evaluation_v2.runner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
