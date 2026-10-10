"""Evaluate generation on a saved RAG run's fixed evidence."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "backend"))

from tests.evaluation_v2.generation_replay import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
